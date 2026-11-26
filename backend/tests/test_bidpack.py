"""Bid synopsis facts and pre-bid query ranking / tender-format export (app.modules.rfp.bidpack). No AI calls."""
import io

from docx import Document
from openpyxl import load_workbook

from app.modules.rfp import bidpack, exports


def _q(rank, query, impact="Medium", **kw):
    return {"rank": rank, "impact": impact, "category": "Other", "document": "Vol I", "section": "", "page": "12",
            "clause_no": f"4.{rank}", "ref": f"Vol I p.12 cl.4.{rank}", "clause_text": "clause", "query": query,
            "suggested_change": "", "reason": "", **kw}


def test_facts_list_orders_and_fills_missing():
    rows = bidpack.facts_list({"emd": {"value": "INR 5,00,000", "ref": "p.3"}})
    assert len(rows) == len(bidpack.BID_FACTS)
    assert rows[0]["item"] == bidpack.BID_FACTS[0][1] and rows[0]["value"] == bidpack.NOT_STATED
    emd = next(r for r in rows if r["item"].startswith("EMD"))
    assert emd == {"item": "EMD / bid security", "value": "INR 5,00,000", "ref": "p.3"}
    assert bidpack.facts_list(rows) is rows  # already converted


def test_merge_keeps_stated_facts_and_first_found_format():
    merged = {}
    bidpack.merge_outputs(merged, {"bid_facts": {"emd": {"value": "Not stated", "ref": ""}, "pbg": {"value": "5%", "ref": "p.9"}},
                                   "tender_format": {"found": False, "columns": []}, "queries": [_q(1, "a")], "summary": "one"})
    bidpack.merge_outputs(merged, {"bid_facts": {"emd": {"value": "INR 2 lakh", "ref": "p.40"}, "pbg": {"value": "Not stated", "ref": ""}},
                                   "tender_format": {"found": True, "columns": [{"heading": "Sr", "field": "sl_no"}]},
                                   "queries": [_q(1, "b")], "summary": "two"})
    assert merged["bid_facts"]["emd"]["value"] == "INR 2 lakh"
    assert merged["bid_facts"]["pbg"]["value"] == "5%"
    assert merged["tender_format"]["found"] is True
    assert [q["query"] for q in merged["queries"]] == ["a", "b"]
    assert merged["summary"] == "one\n\ntwo"


def test_finalise_prebid_ranks_dedupes_and_selects_top_ten():
    qs = [_q(i, f"Query {i}") for i in range(14, 0, -1)] + [_q(2, "query  2")]  # duplicate of rank 2 (case/space)
    out = bidpack.finalise_prebid({"queries": qs})
    assert [q["rank"] for q in out["queries"]] == list(range(1, 15))
    assert out["queries"][0]["query"] == "Query 1"
    assert sum(q["selected"] for q in out["queries"]) == bidpack.TOP_N
    assert out["tender_format"]["found"] is False


def test_selected_queries_respects_user_choice_and_old_runs():
    out = {"queries": [_q(1, "a", selected=False), _q(2, "b", selected=True), _q(3, "c", selected=True)]}
    assert [q["query"] for q in bidpack.selected_queries(out)] == ["b", "c"]
    old = {"queries": [{"ref": "p.1", "clause_text": "x", "query": f"q{i}", "reason": ""} for i in range(12)]}
    assert len(bidpack.selected_queries(old)) == 10


def test_prebid_table_uses_tender_columns():
    out = bidpack.finalise_prebid({"queries": [_q(1, "Relax turnover to INR 50 crore", suggested_change="50 crore")],
                                   "tender_format": {"found": True, "ref": "Annex 3", "instructions": "",
                                                     "columns": [{"heading": "S. No.", "field": "sl_no"},
                                                                 {"heading": "Page", "field": "page"},
                                                                 {"heading": "Clause", "field": "clause_no"},
                                                                 {"heading": "Query", "field": "query"},
                                                                 {"heading": "Bidder remarks", "field": "blank"}]}})
    headers, rows = bidpack.prebid_table(out)
    assert headers == ["S. No.", "Page", "Clause", "Query", "Bidder remarks"]
    assert rows == [["1", "12", "4.1", "Relax turnover to INR 50 crore", ""]]


def test_prebid_table_standard_format_and_old_run_fallback():
    headers, rows = bidpack.prebid_table({"queries": [{"ref": "p.7 cl.2", "clause_text": "c", "query": "q", "reason": "r"}]})
    assert headers == [c["heading"] for c in bidpack.STANDARD_COLUMNS]
    row = dict(zip(headers, rows[0]))
    assert row["Clause No."] == "p.7 cl.2" and row["Clarification Sought"] == "q" and row["Sl. No."] == "1"


def test_prebid_exports_open():
    out = bidpack.finalise_prebid({"queries": [_q(i, f"Query {i}") for i in range(1, 13)],
                                   "tender_format": {"found": True, "ref": "", "instructions": "Email to cpo@example.gov.in",
                                                     "columns": [{"heading": "Sl", "field": "sl_no"}, {"heading": "Query", "field": "query"}]}})
    ws = load_workbook(io.BytesIO(exports.prebid_sheet("Test RFP", out)))["Pre-bid queries"]
    assert [c.value for c in ws[3]] == ["Sl", "Query"]
    assert ws.max_row == 3 + bidpack.TOP_N
    doc = Document(io.BytesIO(exports.prebid_docx("Test RFP", out)))
    assert len(doc.tables[0].rows) == 1 + bidpack.TOP_N
    assert any("cpo@example.gov.in" in p.text for p in doc.paragraphs)


def test_report_starts_with_bid_synopsis():
    runs = {"analysis": bidpack.finalise_analysis({"bid_facts": {"emd": {"value": "INR 1 lakh", "ref": "p.2"}},
                                                   "red_flags": [{"issue": "Unlimited liability", "impact": "High", "ref": "p.50"}],
                                                   "summary": "s", "dates": [{"item": "Bid due", "date": "1 Dec 2026", "ref": "p.1"}]}),
            "prebid": bidpack.finalise_prebid({"queries": [_q(1, "q")]})}
    doc = Document(io.BytesIO(exports.report_docx("Test", runs)))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert headings[0] == "Bid synopsis"
    assert doc.tables[0].rows[0].cells[0].text == "Item"
