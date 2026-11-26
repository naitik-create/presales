"""Docs site crawl helpers, past pre-bid query sheets and compliance-sheet preview. No database or network."""
import pytest

from app.modules.knowledge import prebid_sheet, sites
from app.modules.knowledge.compliance_sheet import parse_rows as parse_compliance

BASE = "https://docs.motadata.com/observeops-docs/"


def test_base_url_and_scope():
    assert sites.base_url("HTTPS://Docs.Motadata.com/observeops-docs?x=1#top") == BASE
    with pytest.raises(ValueError):
        sites.base_url("docs.motadata.com/observeops-docs")
    ex = sites.DEFAULT_EXCLUDE
    assert sites.in_scope(BASE + "Adding%20and%20Managing%20Devices/credential-profile/jdbc", BASE, ex)
    assert sites.in_scope("https://docs.motadata.com/observeops-docs", BASE, ex)  # the start page without "/"
    assert not sites.in_scope("https://docs.motadata.com/serviceops-docs/faqs", BASE, ex)  # another site
    assert not sites.in_scope("https://docs.motadata.com/observeops-docsx/a", BASE, ex)
    assert not sites.in_scope(BASE + "img/logo.png", BASE, ex)
    assert not sites.in_scope(BASE + "markdown-page", BASE, ex)
    assert not sites.in_scope("https://evil.example/observeops-docs/a", BASE, ex)


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.motadata.com/observeops-docs/markdown-page</loc></url>
<url><loc>https://www.motadata.com/observeops-docs/</loc></url>
<url><loc>https://www.motadata.com/observeops-docs/Adding%20and%20Managing%20Devices/credential-profile/jdbc</loc></url>
<url><loc>https://www.motadata.com/observeops-docs/Adding%20and%20Managing%20Devices/credential-profile/jdbc/</loc></url>
<url><loc>https://www.motadata.com/blog/some-post</loc></url>
<url><loc>https://www.motadata.com/observeops-docs/getting-started/overview#install</loc></url>
</urlset>"""


def test_sitemap_on_the_wrong_host_is_moved_to_the_site():
    urls, children = sites.parse_sitemap(SITEMAP)
    assert len(urls) == 6 and children == []
    scoped, truncated = sites.scope_urls(urls, BASE, sites.DEFAULT_EXCLUDE, 100)
    assert scoped == [BASE, BASE + "Adding%20and%20Managing%20Devices/credential-profile/jdbc",
                      BASE + "getting-started/overview"]
    assert not truncated
    assert sites.scope_urls(urls, BASE, sites.DEFAULT_EXCLUDE, 2) == (scoped[:2], True)
    index = '<sitemapindex xmlns="x"><sitemap><loc>https://docs.motadata.com/a.xml</loc></sitemap></sitemapindex>'
    assert sites.parse_sitemap(index) == ([], ["https://docs.motadata.com/a.xml"])
    assert sites.parse_sitemap("<html>not xml") == ([], [])


def test_links_stay_inside_the_site():
    html = """<a href="/observeops-docs/intro">Intro</a> <a href='../faq/'>FAQ</a>
              <a href="https://docs.motadata.com/serviceops-docs/x">Other</a> <a href="#top">Top</a>
              <a href="/observeops-docs/img/a.png">img</a> <a href="mailto:a@b.c">mail</a>"""
    assert sites.links(html, BASE + "start/page", BASE, sites.DEFAULT_EXCLUDE) == [
        BASE + "intro", BASE + "faq"]


PAGE = """<html><head><title>JDBC Credential Profile | ObserveOps</title></head><body>
<nav class="navbar">Menu</nav><main><article>
<nav class="theme-doc-breadcrumbs breadcrumbs">Home &gt; Credentials</nav>
<h1>JDBC Credential Profile in ObserveOps<a class="hash-link" href="#x">​</a></h1>
<p>Use the JDBC protocol to connect to database servers.</p>
<h2>Required Fields<a class="hash-link" href="#r">​</a></h2><ul><li>User Name</li></ul>
<div class="theme-doc-toc-mobile tocCollapsible"><ul class="table-of-contents"><li>Required Fields</li></ul></div>
<nav class="pagination-nav"><a>Previous</a></nav>
</article></main></body></html>"""


def test_page_text_without_navigation():
    from app.parsing.extract import html_to_segments
    segs = html_to_segments(sites.strip_chrome(PAGE), "u").segments
    assert [(s.section, s.text) for s in segs] == [
        ("JDBC Credential Profile in ObserveOps", "Use the JDBC protocol to connect to database servers."),
        ("JDBC Credential Profile in ObserveOps > Required Fields", "User Name")]
    assert sites.page_title(PAGE, "u") == "JDBC Credential Profile in ObserveOps"
    assert sites.page_title("<title>Release notes | Docs</title>", "u") == "Release notes"
    assert sites.page_title("", BASE + "getting-started/system-requirements") == "system requirements"


def test_change_detection():
    a = sites.text_hash([("H", "Some   text")])
    assert a == sites.text_hash([("H", "Some text")]) != sites.text_hash([("H", "Some text!")])
    existing = {"u1": "h1", "u2": "h2", "u3": "h3"}
    plan = sites.plan_changes(existing, {"u1": "h1", "u2": "new", "u4": "h4", "u5": ""}, complete=True)
    assert plan == {"new": ["u4"], "changed": ["u2"], "unchanged": ["u1"], "removed": ["u3"]}
    assert sites.plan_changes(existing, {"u1": "h1"}, complete=False)["removed"] == []
    with pytest.raises(ValueError):
        sites.read_manifest(b'{"base": "x"}')


PREBID_ROWS = [
    ("Sheet1", "Sheet1!R1", ["Pre-bid queries - ACME NMS tender"]),
    ("Sheet1", "Sheet1!R2", ["Sl. No.", "Page No.", "Clause No.", "Existing Clause", "Clarification Sought",
                             "Suggested Change", "Response of ACME"]),
    ("Sheet1", "Sheet1!R3", ["1", "12", "4.2", "OEM turnover Rs 500 crore", "Please relax the OEM turnover to Rs 50 crore",
                             "OEM turnover Rs 50 crore", "Accepted. Revised to Rs 100 crore."]),
    ("Sheet1", "Sheet1!R4", ["2", "", "", "", "Ok", "", ""]),  # too short to be a query
    ("Sheet1", "Sheet1!R5", ["3", "40", "9.1", "Log retention 3 years online",
                             "Kindly confirm whether 1 year online and 2 years archive is acceptable", "", "No change"]),
]


def test_prebid_sheet():
    queries, cols = prebid_sheet.parse_rows(PREBID_ROWS)
    assert cols == [{"sheet": "Sheet1", "query": "Clarification Sought", "reply": "Response of ACME",
                     "suggested_change": "Suggested Change", "clause_text": "Existing Clause", "page": "Page No.",
                     "clause_no": "Clause No.", "sl_no": "Sl. No."}]
    assert [q["query"][:20] for q in queries] == ["Please relax the OEM", "Kindly confirm wheth"]
    assert queries[0]["reply"] == "Accepted. Revised to Rs 100 crore." and queries[0]["ref"] == "Sheet1!R3"
    md = prebid_sheet.to_markdown({"customer": "ACME", "tender": "NMS 2025", "outcome": "Won"}, queries)
    assert md.startswith("# Past pre-bid queries - ACME\nCustomer: ACME. Tender: NMS 2025.")
    assert "## Query 1 (clause 4.2, page 12)\nRFP clause: OEM turnover Rs 500 crore" in md
    assert "Authority's reply: Accepted. Revised to Rs 100 crore." in md and "Change requested: OEM turnover Rs 50 crore" in md
    assert prebid_sheet.parse_rows([("S", "r1", ["Name", "Value"]), ("S", "r2", ["a", "b"])]) == ([], [])


def test_compliance_preview_reports_columns():
    rows = [("Tech", "Tech!R1", ["Sr. No.", "Technical Specification", "Compliance (Y/N)", "Bidder's Remarks"]),
            ("Tech", "Tech!R2", ["1", "The solution shall support SNMP v1/v2c/v3", "Y", "Supported out of the box"]),
            ("Tech", "Tech!R3", ["2", "short", "Y", ""])]
    pairs, cols = parse_compliance(rows)
    assert cols == [{"sheet": "Tech", "requirement": "Technical Specification", "status": "Compliance (Y/N)",
                     "response": "Bidder's Remarks", "ref": "Sr. No."}]
    assert pairs == [{"requirement": "The solution shall support SNMP v1/v2c/v3", "status": "Y",
                      "response": "Supported out of the box", "reference": "Tech!R2 1"}]
