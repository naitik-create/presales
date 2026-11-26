"""Chat about one RFP (app.modules.rfp.rfpchat). No AI or database."""
import json

import pytest

from app.modules.rfp import bidparams, rfpchat

SEGMENTS = [
    "The bidder shall submit EMD of Rs. 10,00,000 in the form of a bank guarantee.",
    "The system shall retain logs for 3 years online and 7 years offline.",
    "Liquidated damages: 0.5% per week of delay, capped at 10% of the contract value.",
    "The OEM shall have an average annual turnover of Rs 100 crore in the last three financial years.",
    "General instructions to bidders.",
]


def test_rank_finds_the_clause():
    assert rfpchat.rank("What is the EMD amount?", SEGMENTS, 2)[0] == 0
    assert rfpchat.rank("how long must logs be retained", SEGMENTS, 2)[0] == 1
    assert rfpchat.rank("Is the penalty for delay capped?", SEGMENTS, 3)[0] == 2
    assert rfpchat.rank("OEM turnover criterion", SEGMENTS, 1) == [3]
    assert rfpchat.rank("the and of", SEGMENTS, 3) == []  # only stop words
    assert rfpchat.tokens("Clause 7.3 asks R045 for 24x7") == ["clause", "7.3", "asks", "r045", "24x7"]


def _strict(schema):
    """Every object in a structured-output schema must list all its properties as required."""
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
        for p in schema["properties"].values():
            _strict(p)
    if schema.get("type") == "array":
        _strict(schema["items"])


def test_schema_and_prompt():
    _strict(rfpchat.CHAT_SCHEMA)
    p = rfpchat.system_prompt()
    assert "architecture (one of: standalone, ha, dr, ha_dr)" in p and "log_retention_days" in p
    assert "Never give prices" in p


CURRENT = {"params": bidparams.clean({"customer_name": "ACME", "monitoring_nodes": 100, "technicians": 10}),
           "sizing_inputs": [{"name": "devices", "value": 100, "ref": "p.4", "note": ""},
                             {"name": "technicians", "value": 10, "ref": "p.9", "note": ""}]}


def test_boq_preview():
    params, sizing, preview = rfpchat.boq_preview(
        [{"name": "architecture", "value": "dr"}, {"name": "technicians", "value": "25"}, {"name": "log_eps", "value": "2,000"}],
        CURRENT)
    assert params["architecture"] == "dr" and params["technicians"] == 25
    assert sizing == {"devices": 100, "technicians": 25, "log_eps": 2000}
    rows = {(r["target"], r["name"]): (r["before"], r["after"]) for r in preview}
    assert rows == {("param", "architecture"): ("standalone", "dr"), ("param", "technicians"): (10, 25),
                    ("sizing", "technicians"): (10, 25), ("sizing", "log_eps"): ("", 2000)}
    with pytest.raises(ValueError, match="Unknown bid parameter"):
        rfpchat.boq_preview([{"name": "price", "value": "1"}], CURRENT)
    with pytest.raises(ValueError):
        rfpchat.boq_preview([{"name": "architecture", "value": "triple"}], CURRENT)
    with pytest.raises(ValueError, match="not a number"):
        rfpchat.boq_preview([{"name": "devices", "value": "many"}], CURRENT)


def test_check_actions():
    numbers = {"R045": 45, "R046": 46}
    acts = rfpchat.check_actions([
        {"stage": "prebid", "summary": "Add a query on log retention", "instruction": "Add a query asking to reduce log retention to 1 year (p.12)",
         "requirement_numbers": [], "param_changes": []},
        {"stage": "compliance", "summary": "R045 partial", "instruction": "Make it Partially Compliant",
         "requirement_numbers": ["r045", "R999"], "param_changes": []},
        {"stage": "boq", "summary": "DC + DR", "instruction": "", "requirement_numbers": [],
         "param_changes": [{"name": "architecture", "value": "dr"}]},
        {"stage": "boq", "summary": "x", "instruction": "", "requirement_numbers": [], "param_changes": []},
    ], numbers, CURRENT)
    assert len(acts) == rfpchat.MAX_ACTIONS
    assert acts[0]["kind"] == "revise" and acts[0]["state"] == "proposed" and acts[0]["label"] == "Pre-bid queries"
    assert acts[1]["requirement_numbers"] == ["R045"] and acts[1]["requirement_ids"] == [45]
    assert acts[2]["kind"] == "params" and acts[2]["preview"][0]["after"] == "dr"
    bad = rfpchat.check_actions([{"stage": "compliance", "summary": "", "instruction": "x y z", "requirement_numbers": ["R1"],
                                  "param_changes": []},
                                 {"stage": "boq", "summary": "", "instruction": "", "requirement_numbers": [],
                                  "param_changes": [{"name": "monitoring_nodes", "value": "100"}]},
                                 {"stage": "nonsense", "summary": "", "instruction": "", "requirement_numbers": [], "param_changes": []}],
                                numbers, CURRENT)
    assert [(a["state"], a["error"]) for a in bad] == [("invalid", "No matching requirement numbers"),
                                                       ("invalid", "The values are already as proposed")]


def test_workspace_material_is_compact_and_unpriced():
    runs = {"analysis": {"summary": "NMS for 40 sites", "bid_facts": [{"item": "EMD", "value": "Rs 10 lakh", "ref": "p.3"}],
                         "objectives": ["not sent"]},
            "prebid": {"queries": [{"rank": 1, "selected": True, "ref": "p.12", "query": "Reduce retention?", "reason": "internal"}]},
            "architecture": {"motadata_sizing": {"architecture": "ha", "sites": [{"title": "DC", "rows": [
                {"n": "Collector", "q": 2, "c": 8, "r": 32, "k": 500}]}]}}}
    m = json.loads(rfpchat.workspace_material(runs, None, {"total": 3}, {"Synopsis": "approved"}))
    assert m["synopsis"]["summary"] == "NMS for 40 sites" and "objectives" not in m["synopsis"]
    assert m["prebid_queries"] == [{"rank": 1, "submit": True, "ref": "p.12", "query": "Reduce retention?"}]
    assert m["hardware_sizing"]["servers"][0]["rows"] == ["2 x Collector: 8 vCPU, 32 GB RAM, 500 GB disk"]
    assert m["step_status"] == {"Synopsis": "approved"}
    assert "price" not in json.dumps(m).lower()
