"""Chat about one RFP: finding the relevant RFP passages, the workspace material the model sees, the answer schema,
and checking the changes the model proposes. Pure functions (no database or AI) so they are easy to test."""
from __future__ import annotations

import json
import math
import re

from app.modules.rfp import bidparams, hwsizing
from app.modules.rfp import workflow as W

MAX_ACTIONS = 3
_STOP = set("""a an and are as at be been but by can could do does for from had has have how i if in into is it its
may me more most must my no not of on or our shall should so than that the their them then there these they this to
up us was we what when where which who why will with would you your rfp tender bidder bidders please tell show give
list any all also about per under""".split())

S = {"type": "string"}
SA = {"type": "array", "items": S}


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


CHAT_SCHEMA = _obj({
    "answer": S,
    "not_found": {"type": "boolean"},
    "citations": SA,
    "actions": {"type": "array", "items": _obj({
        "stage": {"type": "string", "enum": [s["key"] for s in W.STAGES]},
        "summary": S, "instruction": S, "requirement_numbers": SA,
        "param_changes": {"type": "array", "items": _obj({"name": S, "value": S})}})}})


def system_prompt() -> str:
    fields = "\n".join(f"  - {f['name']}: {f['label']}" + (f" (one of: {', '.join(o['value'] for o in f['options'])})"
                                                           if f["options"] else "") for f in bidparams.fields_meta())
    sizing = "\n".join(f"  - {k}: {label}" for k, (label, _p) in hwsizing.INPUTS.items())
    return f"""You are the presales team's assistant for one customer RFP that Motadata (software OEM for ObserveOps
and ServiceOps, bidding through a partner) is bidding for.

Answer from the material supplied: RFP passages (ids D1, D2...), RFP requirements with Motadata's compliance answers
(ids R1, R2...), the team's working outputs for this bid (synopsis, scope, key considerations, pre-bid queries,
bid parameters, hardware sizing), approved Motadata knowledge (ids S1...) and answers from past submitted bids
(ids P1...). Quote amounts, dates, percentages and durations exactly as the RFP states them and cite the ids you used,
inline as [D3] and in citations. Say which RFP page or clause it is. When the material does not answer the question,
set not_found to true and say what is missing; do not guess or use general knowledge about tenders.
Answer in short Markdown: the direct answer first, then the detail. Never give prices.

When the user asks to change something in the bid, do not pretend it is done: propose it in actions (at most
{MAX_ACTIONS}) and say in the answer that it is proposed for the team to apply. Each action names the step it changes:
- synopsis, scope, considerations, prebid: write instruction as a precise instruction for revising that step
  (what to add, change or remove, with RFP references).
- compliance: list the requirement numbers (for example R045) in requirement_numbers and the change in instruction.
- boq: bid parameters and hardware sizing inputs; give param_changes with the field name and the new value.
  Bid parameter fields:
{fields}
  Hardware sizing inputs (numbers):
{sizing}
summary is one line saying what will change. Leave actions empty for plain questions."""


# ---------- finding the relevant RFP text ----------
def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9.\-/]*[a-z0-9]|[a-z0-9]", (text or "").lower())
            if (len(t) > 2 or t.isdigit()) and t not in _STOP]


def rank(query: str, texts: list[str], top_k: int) -> list[int]:
    """Indices of the texts that best match the query: matched query terms weighted by rarity (IDF), favouring
    passages that contain several different terms. Plain keyword search: RFP wording is quoted back literally."""
    q = list(dict.fromkeys(tokens(query)))
    if not q or not texts:
        return []
    docs = [set(tokens(t)) for t in texts]
    n = len(docs)
    idf = {t: math.log(1 + n / (1 + sum(1 for d in docs if t in d))) for t in q}
    scored = []
    for i, d in enumerate(docs):
        hit = [t for t in q if t in d]
        if hit:
            scored.append((sum(idf[t] for t in hit) * (1 + 0.3 * (len(hit) - 1)), i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [i for _s, i in scored[:top_k]]


# ---------- the team's working outputs, compact ----------
def workspace_material(runs: dict, params: dict | None, compliance: dict, stage_status: dict) -> str:
    a, sc, cons, pb = (runs.get(k) or {} for k in ("analysis", "scope", "considerations", "prebid"))
    arch = runs.get("architecture") or {}
    hw = (params or {}).get("sizing") or arch.get("motadata_sizing") or {}
    out = {
        "step_status": stage_status,
        "synopsis": {"summary": a.get("summary"), "bid_facts": a.get("bid_facts"), "key_dates": a.get("dates"),
                     "red_flags": a.get("red_flags"), "mandatory_conditions": a.get("mandatory_conditions"),
                     "missing_information": a.get("missing_information")},
        "scope": {k: sc.get(k) for k in ("owner_counts", "modules_in_scope", "partner_items", "customer_prerequisites",
                                         "out_of_scope", "motadata_gaps")},
        "key_considerations": cons.get("items"), "bid_view": cons.get("bid_view"),
        "prebid_queries": [{"rank": q.get("rank"), "submit": q.get("selected"), "ref": q.get("ref"),
                            "query": q.get("query")} for q in pb.get("queries") or []],
        "compliance_counts": compliance,
        "bid_parameters": (params or {}).get("params"),
        "hardware_sizing": {"architecture": hw.get("architecture"), "topology": hw.get("topology"),
                            "inputs": [{"name": i.get("name"), "value": i.get("value"), "ref": i.get("ref")}
                                       for i in hw.get("inputs") or []],
                            "servers": [{"site": s["title"], "rows": [f"{r['q']} x {r['n']}: {r['c']} vCPU, {r['r']} GB RAM, "
                                                                     f"{r['k']} GB disk" for r in s["rows"]]}
                                        for s in hw.get("sites") or []], "error": hw.get("error")},
    }
    return json.dumps(out, ensure_ascii=False, default=str)[:120_000]


# ---------- proposed changes ----------
def _num(v):
    try:
        f = float(str(v).replace(",", "").strip())
    except ValueError:
        raise ValueError(f"{v!r} is not a number")
    return int(f) if f.is_integer() else f


def boq_preview(changes: list[dict], current: dict) -> tuple[dict, dict, list[dict]]:
    """Validate bid parameter / sizing input changes against the current ones. A name that is both a bid parameter
    and a sizing input (technicians, assets, rum_apps) changes both. Returns (params, sizing input values by name,
    preview rows [{name, label, before, after}]). Raises ValueError for unknown names or bad values."""
    params = dict(current.get("params") or {})
    sizing = {i["name"]: i["value"] for i in current.get("sizing_inputs") or []}
    new_params, new_sizing = dict(params), dict(sizing)
    for ch in changes:
        name, value = (ch.get("name") or "").strip(), ch.get("value")
        if name not in bidparams.NAMES and name not in hwsizing.INPUTS:
            raise ValueError(f"Unknown bid parameter {name!r}")
        if name in bidparams.NAMES:
            new_params[name] = value
        if name in hwsizing.INPUTS:
            new_sizing[name] = _num(value)
    new_params = bidparams.clean(new_params)
    preview = []
    for f in bidparams.fields_meta():
        if params.get(f["name"]) != new_params.get(f["name"]):
            preview.append({"target": "param", "name": f["name"], "label": f["label"], "before": params.get(f["name"], ""),
                            "after": new_params.get(f["name"])})
    for name, (label, _p) in hwsizing.INPUTS.items():
        if sizing.get(name) != new_sizing.get(name):
            preview.append({"target": "sizing", "name": name, "label": f"{label} (sizing)", "before": sizing.get(name, ""),
                            "after": new_sizing.get(name)})
    return new_params, new_sizing, preview


def check_actions(actions: list[dict], numbers: dict[str, int], bid_params: dict | None) -> list[dict]:
    """Keep the proposed changes that can be applied: known step, known requirement numbers, valid parameters.
    Each kept action gets kind ("revise" or "params") and state "proposed"; problems are explained, not dropped."""
    out = []
    for a in (actions or [])[:MAX_ACTIONS]:
        stage = a.get("stage")
        if stage not in W.BY_KEY:
            continue
        act = {"stage": stage, "label": W.BY_KEY[stage]["label"], "summary": (a.get("summary") or "").strip()[:300],
               "instruction": (a.get("instruction") or "").strip()[:2000], "state": "proposed", "error": ""}
        if stage == "boq":
            act["kind"] = "params"
            try:
                params, sizing, preview = boq_preview(a.get("param_changes") or [], bid_params or {})
                if not preview:
                    raise ValueError("The values are already as proposed")
                act.update(params=params, sizing=sizing, preview=preview)
            except ValueError as e:
                act.update(state="invalid", error=str(e))
        else:
            act["kind"] = "revise"
            if stage == "compliance":
                nums = [n.strip().upper() for n in a.get("requirement_numbers") or [] if n.strip().upper() in numbers]
                act["requirement_numbers"] = nums
                act["requirement_ids"] = [numbers[n] for n in nums]
                if not nums:
                    act.update(state="invalid", error="No matching requirement numbers")
            if len(act["instruction"]) < 3:
                act.update(state="invalid", error="No instruction")
        out.append(act)
    return out
