"""Encrypted API keys and logo uploads."""
import pytest
from sqlalchemy import text

from tests.conftest import HEADERS, login

pytestmark = pytest.mark.usefixtures("clean_db")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def admin(client, clean_db):
    login(client, "admin", clean_db)
    return client


def test_api_key_encrypted_at_rest_and_never_returned(admin, db):
    key = "sk-ant-api03-" + "x" * 40 + "WXYZ"
    r = admin.put("/api/admin/api-keys/anthropic", headers=HEADERS, json={"value": key})
    assert r.status_code == 200, r.text
    assert r.json()["masked"] == "…WXYZ" and r.json()["source"] == "database"
    listing = admin.get("/api/admin/api-keys").text
    assert key not in listing
    stored = db.execute(text("SELECT ciphertext FROM api_credentials WHERE provider='anthropic'")).scalar()
    assert stored and key not in stored and "xxxx" not in stored
    from app.core.secrets import get_secret
    assert get_secret(db, "anthropic") == key
    audit = admin.get("/api/admin/audit?action=api_key").json()
    assert audit and key not in str(audit)


def test_api_key_validation_and_custom_provider(admin):
    assert admin.put("/api/admin/api-keys/anthropic", headers=HEADERS, json={"value": "wrong-prefix-123456"}).status_code == 400
    assert admin.put("/api/admin/api-keys/Bad Name", headers=HEADERS, json={"value": "abcdefgh1234"}).status_code == 400
    r = admin.put("/api/admin/api-keys/mistral", headers=HEADERS, json={"value": "abcdefgh1234", "label": "Mistral"})
    assert r.status_code == 200 and r.json()["custom"] is True
    assert any(k["provider"] == "mistral" for k in admin.get("/api/admin/api-keys").json())
    assert admin.delete("/api/admin/api-keys/mistral", headers=HEADERS).status_code == 200


def test_api_keys_need_permission(admin, client):
    roles = {r["name"]: r["id"] for r in admin.get("/api/admin/roles").json()}
    pw = admin.post("/api/admin/users", headers=HEADERS, json={"username": "eng", "full_name": "Eng",
                                                               "role_ids": [roles["Presales Engineer"]]}).json()["temporary_password"]
    admin.post("/api/auth/logout", headers=HEADERS)
    login(client, "eng", pw)
    assert client.get("/api/admin/api-keys").status_code == 403
    assert client.post("/api/admin/branding/logo", headers=HEADERS, files={"file": ("l.png", PNG, "image/png")}).status_code == 403


def test_logo_upload_serve_and_svg_safety(admin, client):
    assert client.get("/api/branding/logo", follow_redirects=False).status_code == 307  # placeholder before upload
    r = admin.post("/api/admin/branding/logo", headers=HEADERS, files={"file": ("logo.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["logo"]["set"] is True
    admin.post("/api/auth/logout", headers=HEADERS)
    served = client.get("/api/branding/logo")  # public: the sign-in page needs it
    assert served.status_code == 200 and served.content == PNG and "sandbox" in served.headers["content-security-policy"]


def test_svg_with_script_rejected_and_export_needs_png(admin):
    bad = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect/></svg>'
    assert admin.post("/api/admin/branding/logo", headers=HEADERS, files={"file": ("l.svg", bad, "image/svg+xml")}).status_code == 400
    good = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    assert admin.post("/api/admin/branding/logomark", headers=HEADERS, files={"file": ("m.svg", good, "image/svg+xml")}).status_code == 200
    assert admin.post("/api/admin/branding/export", headers=HEADERS, files={"file": ("e.svg", good, "image/svg+xml")}).status_code == 400
    assert admin.post("/api/admin/branding/export", headers=HEADERS, files={"file": ("e.png", b"notapng!", "image/png")}).status_code == 400


def test_usage_report_daily_totals_and_budget(admin, db):
    from decimal import Decimal
    from app.models.ai import AIUsageLog
    db.add(AIUsageLog(module="ask", agent_key="ask_motadata", model_id="claude-opus-5-5", input_tokens=1000,
                      output_tokens=200, estimated_cost=Decimal("0.5")))
    db.commit()
    assert admin.put("/api/admin/budget", headers=HEADERS, json={"amount": 10, "thresholds": [50, 100], "hard_stop": False}).status_code == 200
    u = admin.get("/api/admin/usage").json()
    assert u["totals"]["calls"] == 1 and u["totals"]["cost"] == 0.5
    assert len(u["by_day"]) == 1 and u["by_day"][0]["cost"] == 0.5
    assert u["budget"]["amount"] == 10 and u["budget"]["remaining"] == 9.5
