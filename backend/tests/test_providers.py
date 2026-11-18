"""Agents routed to OpenAI, Azure OpenAI and Gemini models (HTTP calls are mocked)."""
import pytest
from sqlalchemy import select

from app.ai import client as ai
from app.ai import providers
from app.core.secrets import set_secret
from app.models.ai import AgentConfiguration, AIModel, AIUsageLog
from tests.conftest import HEADERS, login

pytestmark = pytest.mark.usefixtures("clean_db")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {"answer": {"type": "string"}}}


def _use(db, provider, model_id, endpoint=""):
    db.add(AIModel(model_id=model_id, label=model_id, provider=provider, endpoint=endpoint))
    cfg = db.scalar(select(AgentConfiguration).where(AgentConfiguration.agent_key == "ask_motadata"))
    cfg.model_id = model_id
    set_secret(db, provider, "test-key-12345678", None)
    db.commit()


def test_openai_route_strict_schema_and_usage(db, monkeypatch):
    _use(db, "openai", "gpt-test")
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"model": "gpt-test", "choices": [{"message": {"content": '{"answer": "yes"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 7}}
    monkeypatch.setattr(providers, "_post", fake_post)
    out = ai.call(db, "ask_motadata", system="s", user="q", schema=SCHEMA)
    assert out == {"answer": "yes"}
    assert seen["url"].endswith("/v1/chat/completions") and seen["headers"]["Authorization"] == "Bearer test-key-12345678"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True
    log = db.scalars(select(AIUsageLog).order_by(AIUsageLog.id.desc())).first()
    assert log.model_id == "gpt-test" and log.input_tokens == 100 and log.output_tokens == 7


def test_gemini_route_strips_unsupported_schema_keywords(db, monkeypatch):
    _use(db, "google", "gemini-test")
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, body=body)
        return {"candidates": [{"content": {"parts": [{"text": '{"answer": "ok"}'}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 3}}
    monkeypatch.setattr(providers, "_post", fake_post)
    assert ai.call(db, "ask_motadata", system="s", user="q", schema=SCHEMA) == {"answer": "ok"}
    assert "gemini-test:generateContent" in seen["url"]
    assert "additionalProperties" not in str(seen["body"]["generationConfig"]["responseSchema"])


def test_azure_route_uses_deployment_and_endpoint(db, monkeypatch):
    _use(db, "azure_openai", "my-deployment", "https://res.openai.azure.com")
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers)
        return {"choices": [{"message": {"content": "plain"}, "finish_reason": "stop"}], "usage": {}}
    monkeypatch.setattr(providers, "_post", fake_post)
    assert ai.call(db, "ask_motadata", system="s", user="q") == "plain"
    assert seen["url"].startswith("https://res.openai.azure.com/openai/deployments/my-deployment/chat/completions")
    assert seen["headers"]["api-key"] == "test-key-12345678"


def test_missing_key_and_output_limit_are_reported(db, monkeypatch):
    db.add(AIModel(model_id="gpt-nokey", label="x", provider="openai"))
    db.scalar(select(AgentConfiguration).where(AgentConfiguration.agent_key == "ask_motadata")).model_id = "gpt-nokey"
    db.commit()
    with pytest.raises(ai.AIError, match="No OpenAI API key"):
        ai.call(db, "ask_motadata", system="s", user="q")
    set_secret(db, "openai", "test-key-12345678", None)
    db.commit()
    monkeypatch.setattr(providers, "_post", lambda *a, **k: {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}], "usage": {}})
    with pytest.raises(ai.AIError, match="output limit"):
        ai.call(db, "ask_motadata", system="s", user="q", schema=SCHEMA)


def test_model_admin_validates_provider(client, clean_db):
    login(client, "admin", clean_db)
    assert client.put("/api/admin/ai/models", headers=HEADERS, json={"model_id": "x", "label": "x", "provider": "acme"}).status_code == 400
    assert client.put("/api/admin/ai/models", headers=HEADERS,
                      json={"model_id": "dep", "label": "Azure", "provider": "azure_openai", "endpoint": ""}).status_code == 400
    r = client.put("/api/admin/ai/models", headers=HEADERS, json={"model_id": "gpt-x", "label": "GPT X", "provider": "openai",
                                                                  "input_per_mtok": 1, "output_per_mtok": 2})
    assert r.status_code == 200
    m = next(m for m in client.get("/api/admin/ai/models").json() if m["model_id"] == "gpt-x")
    assert m["provider"] == "openai"
