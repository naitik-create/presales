"""API tests: authentication, permission enforcement, scoring isolation and integrity, spec pack flow and exports."""
import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from tests.conftest import HEADERS, login

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture()
def admin(client, clean_db):
    login(client, "admin", clean_db)
    return client


def make_user(admin_client, username, role_names, participant=False):
    roles = {r["name"]: r["id"] for r in admin_client.get("/api/admin/roles").json()}
    r = admin_client.post("/api/admin/users", headers=HEADERS, json={
        "username": username, "full_name": username.title(), "role_ids": [roles[n] for n in role_names],
        "is_scoring_participant": participant})
    assert r.status_code == 200, r.text
    return r.json()["temporary_password"]


def test_csrf_header_required(client, clean_db):
    r = client.post("/api/auth/login", json={"username": "admin", "password": clean_db})
    assert r.status_code == 403


def test_login_lockout(client, clean_db):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}, headers=HEADERS)
    r = client.post("/api/auth/login", json={"username": "admin", "password": clean_db}, headers=HEADERS)
    assert r.status_code == 423


def test_new_user_has_no_permissions(admin, client):
    pw = make_user(admin, "nobody", [])
    admin.post("/api/auth/logout", headers=HEADERS)
    me = login(client, "nobody", pw)
    assert me["permissions"] == [] and [n["key"] for n in me["nav"]] == ["dashboard"]
    for path in ("/api/rfp/workspaces", "/api/admin/users", "/api/ask/conversations", "/api/scorecard/overview"):
        assert client.get(path).status_code in (403, 404), path


def test_scoring_invisible_to_non_participants(admin, client):
    pw = make_user(admin, "engineer", ["Presales Engineer"])
    admin.post("/api/auth/logout", headers=HEADERS)
    me = login(client, "engineer", pw)
    assert "scorecard" not in [n["key"] for n in me["nav"]]
    assert client.get("/api/scorecard/overview").status_code == 404
    assert client.get("/api/scorecard/transactions").status_code == 404


def test_scoring_flow_integrity_and_warnings(admin, client, db):
    emp_pw = make_user(admin, "emp", ["Scoring participant"], participant=True)
    cats = admin.get("/api/scorecard/categories").json()
    rule = admin.post("/api/scorecard/rules", headers=HEADERS,
                      json={"category_id": cats[0]["id"], "name": "Tracker not updated", "points": -55}).json()
    emp_id = next(p["id"] for p in admin.get("/api/scorecard/participants").json())
    tx = admin.post("/api/scorecard/transactions", headers=HEADERS,
                    json={"employee_id": emp_id, "rule_id": rule["id"], "reason": "Missed", "evidence": "Tracker log"}).json()
    r = admin.post(f"/api/scorecard/transactions/{tx['id']}/approve", headers=HEADERS, json={"note": ""}).json()
    assert r["score"] == 45 and r["warnings"] == ["First warning"]
    # database refuses edits and deletes of decided transactions and audit records
    with pytest.raises(Exception):
        db.execute(text("UPDATE scoring_transactions SET points = 10 WHERE id = :i"), {"i": tx["id"]})
        db.commit()
    db.rollback()
    with pytest.raises(Exception):
        db.execute(text("DELETE FROM audit_logs"))
        db.commit()
    db.rollback()
    # reversal is a new transaction
    rev = admin.post(f"/api/scorecard/transactions/{tx['id']}/reverse", headers=HEADERS, json={"note": "Logged on leave day"}).json()
    admin.post(f"/api/scorecard/transactions/{rev['id']}/approve", headers=HEADERS, json={"note": ""})
    admin.post("/api/auth/logout", headers=HEADERS)
    login(client, "emp", emp_pw)
    ov = client.get("/api/scorecard/overview").json()
    assert ov["me"]["score"] == 100 and ov["team"] is None
    assert len(client.get("/api/scorecard/transactions").json()) == 2
    warnings = client.get("/api/scorecard/warnings").json()
    assert client.post(f"/api/scorecard/warnings/{warnings[0]['id']}/acknowledge", headers=HEADERS).status_code == 200


def test_knowledge_ingest_approve_and_permission_filtered_search(admin, client):
    import app.handlers  # noqa: F401
    from app.core.jobs import run_one

    sections = {s["key"]: s["id"] for s in admin.get("/api/knowledge/sections").json()}
    doc = b"# Architecture\n\nObserveOps supports high availability with an active-passive application cluster.\n\n" \
          b"# Ports\n\nThe collector uses TCP 443 to reach the main server."
    r = admin.post("/api/knowledge/sources/upload", headers=HEADERS,
                   data={"section_id": sections["architecture_and_deployment"], "title": "HA guide", "product": "ObserveOps"},
                   files={"file": ("ha.md", doc, "text/markdown")})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert admin.post(f"/api/knowledge/sources/{sid}/approve", headers=HEADERS, json={}).status_code == 400  # not ingested yet
    assert run_one("test") is True
    src = admin.get(f"/api/knowledge/sources/{sid}").json()
    assert src["ingest_status"] == "Ready" and src["chunks"] >= 1, src
    assert admin.get("/api/knowledge/search?q=high availability cluster").json() == []  # pending sources are not searchable
    admin.post(f"/api/knowledge/sources/{sid}/approve", headers=HEADERS, json={"note": "ok"})
    hits = admin.get("/api/knowledge/search?q=high availability cluster").json()
    assert hits and hits[0]["title"] == "HA guide" and hits[0]["section_path"] == "Architecture"
    # duplicate upload is detected
    dup = admin.post("/api/knowledge/sources/upload", headers=HEADERS, data={"section_id": sections["datasheets"]},
                     files={"file": ("copy.md", doc, "text/markdown")}).json()
    assert dup["warning"]
    # a role without the section permission retrieves nothing from it
    roles = {x["name"]: x for x in admin.get("/api/admin/roles").json()}
    admin.post("/api/admin/roles", headers=HEADERS, json={"name": "Datasheets only", "permissions": ["ask.use", "knowledge.view.datasheets"]})
    rid = {x["name"]: x["id"] for x in admin.get("/api/admin/roles").json()}["Datasheets only"]
    pw = admin.post("/api/admin/users", headers=HEADERS, json={"username": "ds", "full_name": "DS", "role_ids": [rid]}).json()["temporary_password"]
    assert roles
    admin.post("/api/auth/logout", headers=HEADERS)
    login(client, "ds", pw)
    assert client.get("/api/knowledge/search?q=high availability cluster").json() == []


def test_customer_context_parses_sizes(admin):
    c = admin.post("/api/customers", headers=HEADERS, json={
        "name": "Acme Bank", "industry": "BFSI", "infrastructure": "1,200 network devices, 400 servers, 30 branches, 6k endpoints",
        "competitors": ["SolarWinds"]}).json()
    assert c["parsed_sizes"] == {"network_devices": 1200, "servers": 400, "sites": 30, "endpoints": 6000}


def test_spec_intelligence_removed(admin):
    me = admin.get("/api/auth/me").json()
    assert "spec" not in [n["key"] for n in me["nav"]]
    assert not [p for p in me["permissions"] if p.startswith(("spec.", "clauses."))]
    assert admin.get("/api/spec/packs").status_code == 404
    agents = [a["agent_key"] for a in admin.get("/api/admin/ai/agents").json()]
    assert "clause_tailoring" not in agents and "clause_compliance" not in agents