"""Non-Anthropic chat providers, called over HTTPS with httpx (no extra SDKs).

Each function returns a ProviderResult or raises Retryable (rate limit, timeout, server error) or ProviderError.
Structured output: OpenAI and Azure OpenAI use strict json_schema response formats; Gemini uses responseSchema.
"""
from dataclasses import dataclass

import httpx

AZURE_API_VERSION = "2024-10-21"


@dataclass
class ProviderResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop: str  # ok | max_tokens | refusal


class Retryable(Exception):
    pass


class ProviderError(Exception):
    pass


def _post(url: str, headers: dict, body: dict, timeout: int) -> dict:
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise Retryable(f"Connection problem: {e}") from e
    if r.status_code == 429 or r.status_code >= 500:
        raise Retryable(f"HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code >= 400:
        try:
            detail = r.json().get("error", {})
            detail = detail.get("message", detail) if isinstance(detail, dict) else detail
        except ValueError:
            detail = r.text[:300]
        raise ProviderError(f"HTTP {r.status_code}: {detail}")
    return r.json()


def _chat_messages(system: str, history: list, user: str) -> list:
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]


def _openai_body(system: str, history: list, user: str, schema: dict | None, max_tokens: int) -> dict:
    body: dict = {"messages": _chat_messages(system, history, user), "max_completion_tokens": max_tokens}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "strict": True, "schema": schema}}
    return body


def _openai_result(data: dict, model: str) -> ProviderResult:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    finish = choice.get("finish_reason")
    stop = "refusal" if msg.get("refusal") or finish == "content_filter" else "max_tokens" if finish == "length" else "ok"
    return ProviderResult(msg.get("content") or "", data.get("model") or model, usage.get("prompt_tokens", 0),
                          usage.get("completion_tokens", 0), stop)


def openai_chat(key: str, model: str, system: str, history: list, user: str, schema: dict | None,
                max_tokens: int, timeout: int) -> ProviderResult:
    body = {"model": model, **_openai_body(system, history, user, schema, max_tokens)}
    data = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}, body, timeout)
    return _openai_result(data, model)


def azure_chat(key: str, endpoint: str, deployment: str, system: str, history: list, user: str, schema: dict | None,
               max_tokens: int, timeout: int) -> ProviderResult:
    if not endpoint:
        raise ProviderError("Azure OpenAI models need the resource endpoint (e.g. https://myresource.openai.azure.com)")
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={AZURE_API_VERSION}"
    data = _post(url, {"api-key": key}, _openai_body(system, history, user, schema, max_tokens), timeout)
    return _openai_result(data, deployment)


def _gemini_schema(schema: dict) -> dict:
    """Gemini's responseSchema is an OpenAPI subset: drop keywords it does not accept."""
    if isinstance(schema, dict):
        return {k: _gemini_schema(v) for k, v in schema.items() if k not in ("additionalProperties", "$schema")}
    if isinstance(schema, list):
        return [_gemini_schema(v) for v in schema]
    return schema


def gemini_chat(key: str, model: str, system: str, history: list, user: str, schema: dict | None,
                max_tokens: int, timeout: int) -> ProviderResult:
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in history]
    contents.append({"role": "user", "parts": [{"text": user}]})
    config: dict = {"maxOutputTokens": max_tokens}
    if schema:
        config["responseMimeType"] = "application/json"
        config["responseSchema"] = _gemini_schema(schema)
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": config}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    data = _post(url, {"x-goog-api-key": key}, body, timeout)
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return ProviderResult("", model, 0, 0, "refusal")
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    usage = data.get("usageMetadata") or {}
    finish = cand.get("finishReason")
    stop = "max_tokens" if finish == "MAX_TOKENS" else "refusal" if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST") else "ok"
    return ProviderResult(text, data.get("modelVersion") or model, usage.get("promptTokenCount", 0),
                          usage.get("candidatesTokenCount", 0), stop)


def test_key(provider: str, key: str) -> str:
    """Cheap authenticated call that lists models. Returns a short success message or raises."""
    if provider == "openai":
        r = httpx.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        ids = sorted(m["id"] for m in r.json().get("data", []))
        return f"Connected. {len(ids)} models available"
    if provider == "google":
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key}, timeout=20)
        r.raise_for_status()
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])]
        return f"Connected. {len(names)} models available"
    raise ProviderError("No connection test for this provider")
