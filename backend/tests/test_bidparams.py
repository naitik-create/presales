"""Bid parameters (app.modules.rfp.bidparams), unpriced HW BOQ and the BOQ Generator client. No AI or database;
the BOQ Generator is replaced by an httpx mock transport."""
import io

import httpx
import pytest
from openpyxl import Workbook, load_workbook

from app.modules.rfp import bidparams, boq_client, exports, hwsizing

ANALYSIS = {"bid_facts": [
    {"item": "Issuing authority / buyer", "value": "Gujarat Informatics Ltd", "ref": "p.1"},
    {"item": "Warranty, AMC / ATS period", "value": "3 (three) years comprehensive warranty followed by 2 years AMC", "ref": "p.9"},
    {"item": "Contract period", "value": "5 years", "ref": "p.9"},
    {"item": "SLA and penalties", "value": "Helpdesk 24 x 7; 99.5% uptime", "ref": "p.30"}]}
SCOPE = {"modules_in_scope": [{"product": "ObserveOps", "module": "Network monitoring", "basis": "R001"}]}
INPUTS = hwsizing.clean_inputs([
    {"name": "devices", "value": 18, "ref": "Annex B p.44", "note": ""},
    {"name": "log_eps", "value": 2000, "ref": "p.45", "note": ""},
    {"name": "technicians", "value": 10, "ref": "p.60", "note": ""},
    {"name": "ha", "value": 1, "ref": "p.12", "note": ""}])


def test_prefill_from_rfp():
    out = bidparams.prefill(customer="", products=["ObserveOps", "ServiceOps"], analysis=ANALYSIS, scope=SCOPE,
                            sizing_inputs=INPUTS)
    p, src = out["params"], out["sources"]
    assert set(p) == set(bidparams.NAMES)
    assert p["customer_name"] == "Gujarat Informatics Ltd" and src["customer_name"] == "RFP p.1"
    assert p["product_line"] == "aiops"  # only ObserveOps modules are in Motadata's scope
    assert p["amc_years"] == 3
    assert p["support_window"] == "24x7"
    assert p["architecture"] == "ha"
    assert p["monitoring_nodes"] == 25 and src["monitoring_nodes"] == "RFP Annex B p.44"  # raised to the minimum
    assert p["technicians"] == 10
    assert p["log_ingestion_gb"] == 0
    assert any("log-forwarding devices" in n for n in out["notes"])
    assert any("Monitoring nodes" in n for n in out["notes"])


def test_clean_and_warnings():
    p = bidparams.clean({"customer_name": " ACME ", "monitoring_nodes": "10", "ncm_nodes": 30, "license_type": "perpetual"})
    assert p["customer_name"] == "ACME" and p["monitoring_nodes"] == 10 and p["amc_years"] == 5
    assert "Minimum monitoring nodes is 25." in bidparams.warnings(p)
    with pytest.raises(ValueError):
        bidparams.clean({"license_type": "lifetime"})
    with pytest.raises(ValueError):
        bidparams.clean({"assets": "many"})
    ok = bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100})
    assert bidparams.warnings(ok) == []


def test_boq_request_is_unpriced_and_drops_amc_for_subscription():
    p = bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100, "license_type": "annual"})
    body = bidparams.boq_request(p)
    assert body["force_unpriced"] is True and body["amc_years"] == 0 and body["aiops_type"] == "hybrid"
    assert body["monitoring_nodes"] == 100 and body["customer_name"] == "ACME"


def test_sizing_follows_architecture_chosen_on_review():
    p = bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100, "architecture": "ha_dr", "product_line": "aiops"})
    items = bidparams.sizing_items(p, INPUTS)
    assert {i["name"] for i in items if i["name"] in ("ha", "dr")} == {"ha", "dr"}
    sz = bidparams.compute_sizing(p, INPUTS)
    assert sz["architecture"] == "ha_dr" and len(sz["sites"]) == 3
    assert not any(r["n"] == "Motadata ServiceOps" for s in sz["sites"] for r in s["rows"])  # ObserveOps only


def test_hw_boq_workbook():
    p = bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100, "architecture": "dr"})
    sz = bidparams.compute_sizing(p, INPUTS)
    wb = load_workbook(io.BytesIO(exports.hw_boq_workbook("WS", p, sz)))
    ws = wb["HW BOQ (unpriced)"]
    assert ws.cell(row=1, column=1).value == "Hardware BOQ (unpriced) - ACME"
    assert [c.value for c in ws[3]] == ["Sr. No.", "Item", "Minimum specification", "Qty"]
    assert ws.cell(row=4, column=2).value == "PRODUCTION DC SITE - ACTIVE SETUP"
    assert "vCPU" in ws.cell(row=5, column=3).value
    assert ws.max_column == 4  # no price or amount columns


def _xlsx() -> bytes:
    buf = io.BytesIO()
    Workbook().save(buf)
    return buf.getvalue()


def _transport(login_ok=True, boq_status=200):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/login":
            seen["login"] = req.content.decode()
            if login_ok:
                return httpx.Response(302, headers={"location": "/select", "set-cookie": "session=abc; Path=/"})
            return httpx.Response(200, text="<html>Invalid username or password</html>")
        if req.url.path == "/api/download-boq":
            seen["cookie"] = req.headers.get("cookie", "")
            seen["body"] = req.content.decode()
            if boq_status == 200:
                return httpx.Response(200, content=_xlsx(), headers={"content-type": boq_client.XLSX})
            return httpx.Response(400, json={"error": "Minimum monitoring nodes is 25."})
        return httpx.Response(404)
    return httpx.MockTransport(handler), seen


SETTINGS = boq_client.BoqSettings(BOQ_GENERATOR_URL="http://boq.test:5050", BOQ_GENERATOR_USERNAME="rfp-bot",
                                  BOQ_GENERATOR_PASSWORD="test-only")


def test_boq_client_signs_in_and_downloads_unpriced():
    transport, seen = _transport()
    data = boq_client.unpriced_boq({"customer_name": "ACME", "force_unpriced": True}, SETTINGS, transport)
    assert data[:2] == b"PK"
    assert "username=rfp-bot" in seen["login"]
    assert "session=abc" in seen["cookie"] and '"force_unpriced": true' in seen["body"].replace(":true", ": true")


def test_boq_client_errors():
    with pytest.raises(boq_client.BoqError, match="rejected the sign-in"):
        boq_client.unpriced_boq({}, SETTINGS, _transport(login_ok=False)[0])
    with pytest.raises(boq_client.BoqError, match="Minimum monitoring nodes"):
        boq_client.unpriced_boq({}, SETTINGS, _transport(boq_status=400)[0])
    with pytest.raises(boq_client.BoqError, match="not set up"):
        boq_client.unpriced_boq({}, boq_client.BoqSettings(BOQ_GENERATOR_USERNAME="", BOQ_GENERATOR_PASSWORD=""))


def _sheet(cells: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    for ref, v in cells.items():
        ws[ref] = v
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_price_guard():
    header = {"B3": "Product Name", "F3": "Qty", "G3": "Perpetual Price"}
    boq_client.assert_unpriced(_sheet({**header, "B4": "Monitoring", "E4": 997331, "F4": 1, "H4": 100}))  # unpriced layout
    for bad in ({"G4": 250000}, {"I4": 5000}, {"J4": "=I4*H4"}, {"K9": "=SUM(K1:K8)"}):
        with pytest.raises(boq_client.BoqError, match="Refused"):
            boq_client.assert_unpriced(_sheet({**header, **bad}))


def test_boq_client_refuses_a_priced_file():
    def handler(req):
        if req.url.path == "/login":
            return httpx.Response(302, headers={"location": "/select", "set-cookie": "session=abc; Path=/"})
        return httpx.Response(200, content=_sheet({"G3": "Perpetual Price", "G4": 99}), headers={"content-type": boq_client.XLSX})
    with pytest.raises(boq_client.BoqError, match="price column"):
        boq_client.unpriced_boq({}, SETTINGS, httpx.MockTransport(handler))


def test_bid_pack_zip():
    import zipfile
    from types import SimpleNamespace as NS
    from app.modules.rfp import bidpack
    p = bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100, "architecture": "ha"})
    bp = {"params": p, "sizing": bidparams.compute_sizing(p, INPUTS)}
    rows = [(NS(number="R001", text="Collect syslog", source_file="RFP.pdf", source_ref="p.5", category="Technical"),
             NS(status="Compliant", response="Yes", explanation="", evidence="", sources=[], validation_remarks="",
                origin="ai", approved=False))]
    runs = {"analysis": bidpack.finalise_analysis({"bid_facts": {}, "summary": "s"}),
            "prebid": bidpack.finalise_prebid({"queries": [{"rank": 1, "query": "q", "ref": "p.1", "clause_text": "c"}]})}

    def sw_fail():
        raise boq_client.BoqError("Cannot reach the BOQ Generator")

    data, files = exports.bid_pack("WS", rows, runs, bp, sw_fail)  # every step approved
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    assert "1 Synopsis.docx" in names and "6 Unpriced HW BOQ.xlsx" in names
    assert "6 Unpriced SW BOQ.xlsx" not in names and "2 Scope matrix.xlsx" not in names
    status = {f["name"]: f for f in files}
    assert status["6 Unpriced SW BOQ.xlsx"]["note"] == "Cannot reach the BOQ Generator"
    assert status["2 Scope matrix.xlsx"]["note"] == "Motadata scope has not been run"
    readme = z.read("README.txt").decode()
    assert "No prices are included" in readme and "customer_name: ACME" in readme
    for n in names:  # nothing we build carries formulas
        if n.endswith(".xlsx"):
            wb = load_workbook(io.BytesIO(z.read(n)))
            assert not any(isinstance(c.value, str) and c.value.startswith("=") for ws in wb for r in ws.iter_rows() for c in r)
    data2, files2 = exports.bid_pack("WS", rows, runs, bp, lambda: _sheet({"B3": "Product Name"}))
    assert "6 Unpriced SW BOQ.xlsx" in zipfile.ZipFile(io.BytesIO(data2)).namelist()
