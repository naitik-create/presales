"""Guided bid workflow: the RFP outputs are reviewed one step at a time on the same screen.

Each step can be edited directly or revised by the AI on an instruction (shown as a draft to accept or discard), then
approved. A step's downloads are available only once it is approved. Every change is a new version (a new
RFPAgentRun row), so earlier versions can be restored. When an approved step changes, the approved steps that depend on
it are reopened and marked "needs review" instead of changing silently.

Storage, without migrations:
- step content: the latest RFPAgentRun row of the step's agent; approved = step approved
  (the Compliance step is approved when every active requirement has an approved answer)
- an AI revision waiting for accept / discard: RFPAgentRun row "draft:<step>"
- who approved and why a step needs review: one RFPAgentRun row "workflow_state", updated in place
"""
from __future__ import annotations

import json
import re

from app.modules.rfp import bidpack

STAGES: list[dict] = [
    {"key": "synopsis", "label": "Synopsis", "agent": "analysis", "depends": [],
     "downloads": [("synopsis", "Synopsis (Word)")]},
    {"key": "scope", "label": "Scope matrix", "agent": "scope", "depends": [],
     "downloads": [("scope", "Scope matrix (Excel)")]},
    {"key": "considerations", "label": "Key considerations", "agent": "considerations", "depends": ["synopsis", "scope"],
     "downloads": [("considerations", "Key considerations (Word)")]},
    {"key": "prebid", "label": "Pre-bid queries", "agent": "prebid", "depends": ["synopsis"],
     "downloads": [("prebid", "Pre-bid queries (Excel)"), ("prebid_docx", "Pre-bid queries (Word)")]},
    {"key": "compliance", "label": "Compliance", "agent": None, "depends": [],
     "downloads": [("compliance", "Compliance statement (Excel)")]},
    {"key": "boq", "label": "Sizing and BOQ", "agent": "bid_parameters", "depends": ["synopsis", "scope"],
     "downloads": [("hw_sizing", "HW sizing (Excel)"), ("hw_boq", "Unpriced HW BOQ"), ("sw_boq", "Unpriced SW BOQ")]},
]
BY_KEY = {s["key"]: s for s in STAGES}
STAGE_OF_AGENT = {s["agent"]: s["key"] for s in STAGES if s["agent"]}
EXPORT_STAGE = {kind: s["key"] for s in STAGES for kind, _label in s["downloads"]} | {"considerations_text": "considerations"}
DOC_STAGES = {"synopsis", "scope", "considerations", "prebid"}  # content is one agent output, edited as a whole
REVISABLE = DOC_STAGES | {"compliance"}
STATE_KEY = "workflow_state"
DRAFT_PREFIX = "draft:"
_SKIP = {"citations", "source_ids", "owner_counts"}
_TITLE_KEYS = ("query", "consideration", "issue", "item", "module", "criterion", "text", "number")


def downstream(key: str) -> list[str]:
    """Steps that depend on `key`, directly or through another step, in workflow order."""
    found: set[str] = set()
    todo = [key]
    while todo:
        k = todo.pop()
        for s in STAGES:
            if k in s["depends"] and s["key"] not in found:
                found.add(s["key"])
                todo.append(s["key"])
    return [s["key"] for s in STAGES if s["key"] in found]


# ---------- what an AI revision changed ----------
def _label(path: list[str]) -> str:
    # field names (snake_case) read as words; row names (requirement numbers, fact labels) stay as they are
    return " › ".join(p.replace("_", " ").capitalize() if re.fullmatch(r"[a-z_]+", p) else p for p in path)


def _title(v) -> str:
    if isinstance(v, dict):
        for k in _TITLE_KEYS:
            if v.get(k):
                return str(v[k])
        return json.dumps(v, ensure_ascii=False)[:300]
    return str(v)


def _key_field(old: list, new: list) -> str | None:
    """A field that names each row uniquely in both versions, so rows can be compared one to one."""
    if (old or new) and all(isinstance(i, dict) for i in old + new):
        for k in ("number", "item"):
            if all(len({str(i.get(k)) for i in rows if i.get(k)}) == len(rows) for rows in (old, new)):
                return k
    return None


def diff(old, new, path: list[str] | None = None, out: list[dict] | None = None, limit: int = 80) -> list[dict]:
    """Readable list of changes between two versions of a step: [{where, before, after}]. Lists of rows with a
    requirement number or item name are compared row by row; other lists as added / removed entries."""
    path, out = path or [], [] if out is None else out
    if len(out) >= limit or old == new:
        return out
    if isinstance(old, dict) and isinstance(new, dict):
        for k in list(old) + [k for k in new if k not in old]:
            if k in _SKIP or k.startswith("_"):
                continue
            diff(old.get(k), new.get(k), path + [k], out, limit)
        return out
    if isinstance(old, list) and isinstance(new, list):
        kf = _key_field(old, new)
        if kf:
            before = {str(i[kf]): i for i in old}
            after = {str(i[kf]): i for i in new}
            for k in list(before) + [k for k in after if k not in before]:
                diff(before.get(k), after.get(k), path + [k], out, limit)
            return out
        olds = [json.dumps(i, sort_keys=True, ensure_ascii=False) for i in old]
        news = [json.dumps(i, sort_keys=True, ensure_ascii=False) for i in new]
        for i, s in zip(old, olds):
            if s not in news and len(out) < limit:
                out.append({"where": _label(path), "before": _title(i), "after": ""})
        for i, s in zip(new, news):
            if s not in olds and len(out) < limit:
                out.append({"where": _label(path), "before": "", "after": _title(i)})
        return out
    if isinstance(old, dict) or isinstance(new, dict):
        old_d, new_d = old if isinstance(old, dict) else {}, new if isinstance(new, dict) else {}
        return diff(old_d, new_d, path, out, limit) if (old_d or new_d) else out
    out.append({"where": _label(path), "before": "" if old is None else _title(old),
                "after": "" if new is None else _title(new)})
    return out


# ---------- applying an AI revision ----------
def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def carry_selection(old: dict, new: dict) -> dict:
    """After a revision, keep the team's choice of which pre-bid queries to submit. A query keeps its tick when its
    text, or its reference and clause, match a query in the previous version; new queries are ticked if in the top 10."""
    old_qs = list(old.get("queries") or [])
    has_sel = any("selected" in q for q in old_qs)
    was = {i: (bool(q.get("selected")) if has_sel else i < bidpack.TOP_N) for i, q in enumerate(old_qs)}
    by_text = {_norm(q.get("query")): i for i, q in enumerate(old_qs)}
    by_clause = {(_norm(q.get("ref")), _norm(q.get("clause_text"))): i for i, q in enumerate(old_qs) if q.get("clause_text")}
    queries = [q for q in sorted(new.get("queries") or [], key=lambda q: q.get("rank") or 999) if _norm(q.get("query"))]
    for i, q in enumerate(queries, start=1):
        q["rank"] = i
        prev = by_text.get(_norm(q.get("query")))
        if prev is None:
            prev = by_clause.get((_norm(q.get("ref")), _norm(q.get("clause_text"))))
        q["selected"] = was[prev] if prev is not None else i <= bidpack.TOP_N
    out = {**old, **new, "queries": queries}
    out.setdefault("tender_format", {"found": False, "ref": "", "instructions": "", "columns": []})
    return out


def apply_scope_changes(current: dict, revised: dict) -> dict:
    """Scope revisions return the summary in full and only the matrix rows that change."""
    numbers = [m["number"] for m in current.get("matrix") or []]
    rows = {m["number"]: dict(m) for m in current.get("matrix") or []}
    for ch in revised.get("matrix_changes") or []:
        n = (ch.get("number") or "").strip()
        if n in rows:
            rows[n] = {**rows[n], **ch, "number": n}
    out = {**current, **{k: v for k, v in revised.items() if k != "matrix_changes"}}
    out["matrix"] = [rows[n] for n in numbers]
    return bidpack.finalise_scope(out, numbers)


def apply_revision(stage: str, current: dict, revised: dict) -> dict:
    if stage == "synopsis":
        return bidpack.finalise_analysis({**current, **revised})
    if stage == "scope":
        return apply_scope_changes(current, revised)
    if stage == "prebid":
        return carry_selection(current, revised)
    return {**current, **revised}


def clean_edit(stage: str, current: dict, edited: dict) -> dict:
    """A direct edit from the review screen: keep fields the screen does not send and recompute derived values."""
    out = {**current, **(edited or {})}
    if stage == "synopsis":
        return bidpack.finalise_analysis(out)
    if stage == "scope":
        return bidpack.finalise_scope(out, [m["number"] for m in current.get("matrix") or []])
    if stage == "prebid":
        qs = [q for q in out.get("queries") or [] if _norm(q.get("query"))]
        for i, q in enumerate(qs, start=1):
            q["rank"] = i
            q["selected"] = bool(q.get("selected"))
        out["queries"] = qs
    return out


def considerations_text(ws_name: str, out: dict) -> str:
    """Plain text for pasting into an email to the bid team."""
    lines = [f"Key considerations - {ws_name}", ""]
    view = out.get("bid_view") or {}
    if view.get("recommendation"):
        lines += [f"Indicative bid view: {view['recommendation']}. {view.get('reason', '')}".strip(), ""]
    for i, it in enumerate(out.get("items") or [], start=1):
        ref = f" (RFP {it['ref']})" if it.get("ref") else ""
        lines.append(f"{i}. [{it.get('impact', '')}] {it.get('category', '')}: {it.get('consideration', '')}{ref}")
        if it.get("action"):
            lines.append(f"   Action: {it['action']} - {it.get('owner', '')}")
    return "\n".join(lines) + "\n"
