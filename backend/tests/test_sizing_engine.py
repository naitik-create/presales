"""Motadata hardware sizing (app.modules.rfp.sizing_engine, hwsizing). No AI or database.

fixtures/sizing_parity.json was produced by running the BOQ Generator's oo_sizing.js
(fixtures/gen_sizing_parity.js) over 120 seeded random inputs; the Python port must give identical output."""
import io
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.modules.rfp import exports, hwsizing
from app.modules.rfp import sizing_engine as E

CASES = json.loads((Path(__file__).parent / "fixtures" / "sizing_parity.json").read_text())


def _run(fn):
    try:
        return {"ok": json.loads(json.dumps(fn()))}
    except E.SizingError as e:
        return {"error": str(e)}


@pytest.mark.parametrize("i", range(len(CASES)))
def test_parity_with_boq_generator(i):
    c = CASES[i]
    assert _run(lambda: E.size(c["sizeIn"])) == c["size"]
    assert _run(lambda: E.hardware_sites(E.SERVICEOPS_TABLES, c["hwIn"])) == c["hw"]


def test_fixture_covers_every_topology():
    topologies = {c["size"]["ok"]["topology"] for c in CASES if "ok" in c["size"]}
    assert topologies == {"single", "dist", "ha"}
    assert any("error" in c["size"] for c in CASES)


def test_compute_from_rfp_inputs():
    items = [{"name": "devices", "value": 1200, "ref": "Annex A p.40", "note": "800 network + 400 servers"},
             {"name": "log_eps", "value": 3000, "ref": "p.41", "note": ""},
             {"name": "technicians", "value": 25, "ref": "p.60", "note": ""},
             {"name": "assets", "value": 4000, "ref": "p.60", "note": ""},
             {"name": "dr", "value": 1, "ref": "p.12", "note": ""},
             {"name": "devices", "value": 99, "ref": "p.99", "note": "later window repeats"},
             {"name": "unknown_thing", "value": 5, "ref": "", "note": ""},
             {"name": "log_retention_days", "value": 180, "ref": "p.41", "note": ""}]
    out = hwsizing.compute(items, ["ObserveOps", "ServiceOps"])
    assert out["status"] == "ok"
    assert [i["name"] for i in out["inputs"]] == ["devices", "log_eps", "technicians", "assets", "dr", "log_retention_days"]
    assert out["inputs"][0]["value"] == 1200
    assert out["architecture"] == "dc_dr"
    assert [s["title"] for s in out["sites"]] == ["PRODUCTION DC SITE - ACTIVE SETUP", "PRODUCTION DR SITE - HA SETUP"]
    names = [r["n"] for r in out["sites"][0]["rows"]]
    assert "Motadata ServiceOps" in names and any(n.startswith("Motadata ObserveOps Master") for n in names)
    assert out["engine_input"]["observeInput"]["log"]["mode"] == "gb"
    assert any("EPS" in n for n in out["notes"]) and any("180 days" in n for n in out["notes"])
    assert len(out["fields"]) == len(hwsizing.INPUTS)


def test_compute_respects_products_and_limits():
    assert hwsizing.compute([{"name": "technicians", "value": 10, "ref": "", "note": ""}], ["ObserveOps"])["status"] == "missing_inputs"
    out = hwsizing.compute([{"name": "devices", "value": 20000, "ref": "", "note": ""}], ["ObserveOps"])
    assert out["status"] == "out_of_range" and "Solution Architect" in out["error"]


def test_hw_sizing_workbook():
    out = hwsizing.compute([{"name": "devices", "value": 400, "ref": "p.3", "note": ""},
                            {"name": "ha", "value": 1, "ref": "p.4", "note": ""}], ["ObserveOps"])
    wb = load_workbook(io.BytesIO(exports.hw_sizing_workbook("Test", out)))
    ws = wb["Hardware sizing"]
    assert [c.value for c in ws[3]] == exports.HW_HEADERS
    assert ws.cell(row=4, column=1).value == "PRODUCTION DC SITE - ACTIVE SETUP"
    assert ws.max_row - 3 == sum(len(s["rows"]) for s in out["sites"])
    assert wb["Sizing inputs"].cell(row=2, column=3).value == "p.3"
