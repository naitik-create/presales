"""Guided bid workflow (app.modules.rfp.workflow) and the per-step downloads. No AI or database."""
import io
import zipfile
from types import SimpleNamespace as NS

from docx import Document

from app.modules.rfp import bidpack, exports, workflow as W


def test_steps_and_dependencies():
    assert [s["key"] for s in W.STAGES] == ["synopsis", "scope", "considerations", "prebid", "compliance", "boq"]
    assert W.downstream("synopsis") == ["considerations", "prebid", "boq"]
    assert W.downstream("scope") == ["considerations", "boq"]
    assert W.downstream("considerations") == [] and W.downstream("compliance") == []
    assert W.EXPORT_STAGE["prebid_docx"] == "prebid" and W.EXPORT_STAGE["sw_boq"] == "boq"
    assert W.EXPORT_STAGE["considerations_text"] == "considerations"
    assert "internal" not in W.EXPORT_STAGE and "report" not in W.EXPORT_STAGE  # internal drafts stay available
    assert W.STAGE_OF_AGENT == {"analysis": "synopsis", "scope": "scope", "considerations": "considerations",
                                "prebid": "prebid", "bid_parameters": "boq"}


def test_diff_is_readable():
    old = {"summary": "Old", "bid_facts": [{"item": "EMD / bid security", "value": "Rs 5 lakh", "ref": "p.3"},
                                           {"item": "Tender fee", "value": "Not stated", "ref": ""}],
           "red_flags": [{"issue": "Uncapped LD", "impact": "High", "ref": "p.40"}], "citations": [1]}
    new = {"summary": "New", "bid_facts": [{"item": "EMD / bid security", "value": "Rs 10 lakh", "ref": "p.3"},
                                           {"item": "Tender fee", "value": "Not stated", "ref": ""}],
           "red_flags": [{"issue": "Uncapped LD", "impact": "High", "ref": "p.40"},
                         {"issue": "MAF from OEM within 7 days", "impact": "Medium", "ref": "p.12"}], "citations": [2]}
    ch = W.diff(old, new)
    assert {"where": "Summary", "before": "Old", "after": "New"} in ch
    assert {"where": "Bid facts › EMD / bid security › Value", "before": "Rs 5 lakh", "after": "Rs 10 lakh"} in ch
    assert {"where": "Red flags", "before": "", "after": "MAF from OEM within 7 days"} in ch
    assert len(ch) == 3  # citations ignored, unchanged rows not listed
    assert W.diff(old, old) == []


def test_diff_matrix_by_requirement_number():
    old = {"matrix": [{"number": "R001", "owner": "Motadata"}, {"number": "R002", "owner": "Customer"}]}
    new = {"matrix": [{"number": "R001", "owner": "Partner / SI"}, {"number": "R002", "owner": "Customer"}]}
    assert W.diff(old, new) == [{"where": "Matrix › R001 › Owner", "before": "Motadata", "after": "Partner / SI"}]


def test_scope_revision_changes_only_named_rows():
    current = bidpack.finalise_scope({"matrix": [{"number": "R001", "owner": "Motadata", "product": "ObserveOps",
                                                  "module": "Log management", "note": ""},
                                                 {"number": "R002", "owner": "Customer", "product": "", "module": "", "note": ""}],
                                      "partner_items": [{"item": "Servers", "ref": "p.5"}], "citations": ["c"]},
                                     ["R001", "R002"])
    revised = {"matrix_changes": [{"number": "R002", "owner": "Partner / SI", "product": "", "module": "", "note": "SI supplies"},
                                  {"number": "R999", "owner": "Motadata", "product": "", "module": "", "note": ""}],
               "partner_items": [{"item": "Servers", "ref": "p.5"}, {"item": "OS licences", "ref": "p.6"}],
               "modules_in_scope": [], "customer_prerequisites": [], "out_of_scope": [], "motadata_gaps": []}
    out = W.apply_revision("scope", current, revised)
    assert [m["owner"] for m in out["matrix"]] == ["Motadata", "Partner / SI"]  # unknown R999 ignored
    assert out["matrix"][1]["note"] == "SI supplies" and "matrix_changes" not in out
    assert out["owner_counts"] == [{"owner": "Motadata", "requirements": 1}, {"owner": "Partner / SI", "requirements": 1}]
    assert len(out["partner_items"]) == 2 and out["citations"] == ["c"]


def test_prebid_revision_keeps_the_teams_selection():
    current = {"tender_format": {"found": True, "columns": [{"heading": "Query", "field": "query"}]},
               "queries": [{"rank": i, "query": f"Q{i}", "ref": f"p.{i}", "clause_text": f"C{i}", "selected": i != 2}
                           for i in range(1, 13)]}
    revised = {"tender_format": current["tender_format"],
               "queries": [{"rank": 1, "query": "Q1 reworded", "ref": "p.1", "clause_text": "C1"},  # same clause
                           {"rank": 2, "query": "Q2", "ref": "p.2", "clause_text": "C2"},  # was un-ticked
                           {"rank": 3, "query": "New query", "ref": "p.99", "clause_text": "C99"},
                           {"rank": 4, "query": "Q12", "ref": "p.12", "clause_text": "C12"},  # was ticked
                           {"rank": 5, "query": " ", "ref": "", "clause_text": ""}]}
    out = W.apply_revision("prebid", current, revised)
    assert [(q["rank"], q["query"], q["selected"]) for q in out["queries"]] == [
        (1, "Q1 reworded", True), (2, "Q2", False), (3, "New query", True), (4, "Q12", True)]


def test_synopsis_revision_and_edit_keep_facts_as_list():
    current = bidpack.finalise_analysis({"bid_facts": {"emd": {"value": "Rs 5 lakh", "ref": "p.3"}}, "summary": "s",
                                         "red_flags": []})
    revised = {"bid_facts": {"emd": {"value": "Rs 10 lakh", "ref": "p.3"}}, "summary": "s2",
               "red_flags": [{"issue": "a", "impact": "Low", "ref": ""}, {"issue": "b", "impact": "High", "ref": ""}]}
    out = W.apply_revision("synopsis", current, revised)
    emd = next(f for f in out["bid_facts"] if f["item"] == "EMD / bid security")
    assert emd["value"] == "Rs 10 lakh" and len(out["bid_facts"]) == len(bidpack.BID_FACTS)
    assert [f["issue"] for f in out["red_flags"]] == ["b", "a"]
    edited = W.clean_edit("synopsis", out, {"summary": "Edited"})
    assert edited["summary"] == "Edited" and edited["bid_facts"] == out["bid_facts"]


def test_prebid_edit_drops_empty_and_renumbers():
    out = W.clean_edit("prebid", {"queries": []}, {"queries": [{"query": "A", "selected": True}, {"query": ""},
                                                              {"query": "B"}]})
    assert [(q["rank"], q["query"], q["selected"]) for q in out["queries"]] == [(1, "A", True), (2, "B", False)]


CONS = {"bid_view": {"recommendation": "Go with conditions", "reason": "MAF and PBG need management approval."},
        "items": [{"category": "OEM / MAF", "consideration": "MAF must be on OEM letterhead", "impact": "High",
                   "ref": "p.12", "action": "Arrange MAF", "owner": "Sales"}]}


def test_considerations_text_and_docx():
    text = W.considerations_text("ACME NMS", CONS)
    assert "Indicative bid view: Go with conditions." in text
    assert "1. [High] OEM / MAF: MAF must be on OEM letterhead (RFP p.12)" in text and "Action: Arrange MAF - Sales" in text
    doc = Document(io.BytesIO(exports.considerations_docx("ACME NMS", CONS)))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    assert "MAF must be on OEM letterhead" in cells and "Arrange MAF" in cells


def test_synopsis_docx():
    analysis = bidpack.finalise_analysis({"bid_facts": {"emd": {"value": "Rs 5 lakh", "ref": "p.3"}}, "summary": "Short",
                                          "red_flags": [], "objectives": ["Unified NMS"], "dates": []})
    doc = Document(io.BytesIO(exports.synopsis_docx("ACME", analysis)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Short" in text and "Unified NMS" in text
    assert "Rs 5 lakh" in [c.text for t in doc.tables for row in t.rows for c in row.cells]


def test_bid_pack_holds_only_approved_steps():
    rows = [(NS(number="R001", text="Collect syslog", source_file="RFP.pdf", source_ref="p.5", category="Technical"),
             NS(status="Compliant", response="Yes", explanation="", evidence="", sources=[], validation_remarks="",
                origin="ai", approved=True))]
    runs = {"analysis": bidpack.finalise_analysis({"bid_facts": {}, "summary": "s"}), "considerations": CONS,
            "prebid": bidpack.finalise_prebid({"queries": [{"rank": 1, "query": "q", "ref": "p.1", "clause_text": "c"}]})}

    def never():
        raise AssertionError("SW BOQ must not be requested for an unapproved step")

    data, files = exports.bid_pack("WS", rows, runs, None, never, {"synopsis", "considerations", "compliance"})
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert names == {"1 Synopsis.docx", "3 Key considerations.docx", "5 Compliance statement.xlsx", "README.txt"}
    status = {f["name"]: f for f in files}
    assert status["4 Pre-bid queries (tender format).xlsx"]["note"] == "Step not approved yet"
    assert status["6 Unpriced SW BOQ.xlsx"]["note"] == "Step not approved yet"
    readme = zipfile.ZipFile(io.BytesIO(data)).read("README.txt").decode()
    assert "No prices are included" in readme and "Confirmed bid parameters" not in readme
