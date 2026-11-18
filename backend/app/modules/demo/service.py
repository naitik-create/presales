"""Demo Intelligence (§9). Product steps come from the curated use-case library; anything else is flagged."""
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import client as ai
from app.ai import retrieval
from app.core.jobs import JobContext, handler
from app.core.notify import notify
from app.exports import brand
from app.models.core import CustomerContext, Job
from app.models.demo import DemoProject, DemoScriptVersion, DemoUseCase
from app.models.knowledge import KnowledgeSection
from app.common.text import normalise


def _o(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


S = {"type": "string"}
SA = {"type": "array", "items": S}
SCRIPT_SCHEMA = _o({
    "opening": _o({"customer_context": S, "challenges": SA}),
    "end_result_first": _o({"outcome": S, "how_to_show": S}),
    "agenda": {"type": "array", "items": _o({"use_case_id": S, "title": S, "pain": S, "minutes": {"type": "integer"}})},
    "use_cases": {"type": "array", "items": _o({
        "use_case_id": S, "title": S, "pain": S, "navigation": SA, "what_to_show": S, "value_statement": S,
        "differentiator": S, "differentiator_source": S, "check_in_question": S, "transition": S})},
    "objections": {"type": "array", "items": _o({"objection": S, "answer": S})},
    "closing": _o({"summary": S, "next_steps": SA}),
    "checklist": SA,
})
SYSTEM = """Write a customer-specific product demo script for Motadata.
Structure: opening with the customer context and challenges; show the end result first; an agenda of three or four use cases,
each tied to a stated pain point and sized to fit the duration; then for each use case the pain, navigation and screens,
value statement, differentiator against the named competitor and a check-in question; transition lines; likely objections
with answers; closing summary and next steps; and a pre-demo checklist of data, integrations and accounts.
Take navigation paths, menu names and screen names only from the use-case library (copy them exactly) or the approved
documentation supplied. Never invent them. Set use_case_id to the library id you used, or "" if none.
Differentiators come only from the competitor sources; set differentiator_source to the source id or "" if none applies."""


def use_case_out(u: DemoUseCase) -> dict:
    return {c: getattr(u, c) for c in ("id", "name", "product", "module_key", "pain", "industries", "navigation",
                                       "what_to_show", "expected_result", "talk_track", "value_statement", "differentiator",
                                       "objections", "prerequisites", "minutes", "status")}


def verify_steps(content: dict, library: dict[str, DemoUseCase], doc_text: str) -> list[dict]:
    """Flag any navigation step that is not in the library use case or the approved documentation retrieved."""
    flags = []
    norm_doc = normalise(doc_text)
    for i, uc in enumerate(content.get("use_cases", [])):
        lib = library.get(uc.get("use_case_id", ""))
        lib_steps = {normalise(s) for s in (lib.navigation if lib else [])}
        for j, step in enumerate(uc.get("navigation", [])):
            n = normalise(step)
            if n in lib_steps or (len(n) > 8 and n in norm_doc):
                continue
            flags.append({"use_case": i, "step": j, "text": step, "reason": "Not in the use-case library or approved documentation"})
    return flags


@handler("demo.generate")
def generate(db: Session, job: Job, ctx: JobContext) -> dict:
    p = db.get(DemoProject, job.payload["project_id"])
    inputs = dict(p.inputs)
    if p.customer_id:
        c = db.get(CustomerContext, p.customer_id)
        for k, attr in (("industry", "industry"), ("existing_tools", "existing_tools"), ("infrastructure", "infrastructure"),
                        ("competitors", "competitors"), ("pain_points", "pain_points")):
            inputs.setdefault(k, getattr(c, attr))
        inputs.setdefault("customer", c.name)
    products = inputs.get("products") or ["ObserveOps", "ServiceOps"]
    q = select(DemoUseCase).where(DemoUseCase.status == "Approved", DemoUseCase.product.in_(products))
    exclude = set(inputs.get("exclude_use_cases") or [])
    include = set(inputs.get("include_use_cases") or [])
    ucs = [u for u in db.scalars(q) if str(u.id) not in exclude]
    library = {str(u.id): u for u in ucs}
    allowed = set(db.scalars(select(KnowledgeSection.key)))
    comp_query = f"Motadata versus {', '.join(inputs.get('competitors') or [])} differentiators"
    comp_hits = retrieval.search(db, comp_query, allowed, sections=["competitor_information"], top_k=6, id_prefix="C")
    doc_hits = retrieval.search(db, f"{inputs.get('pain_points', '')} navigation screens", allowed,
                                sections=["specifications", "online_documentation", "datasheets"], top_k=6, id_prefix="D")
    ctx.progress(20, "Writing the demo script")
    lib_json = "\n".join(json.dumps({"id": str(u.id), **{k: v for k, v in use_case_out(u).items() if k != "id"},
                                     "must_include": str(u.id) in include}) for u in ucs)
    user = (f"<inputs>{json.dumps(inputs, default=str)}</inputs>\n<use_case_library>\n{lib_json or '(empty)'}\n</use_case_library>\n"
            f"<competitor_sources>\n{retrieval.format_hits(comp_hits)}\n</competitor_sources>\n"
            f"<documentation>\n{retrieval.format_hits(doc_hits)}\n</documentation>")
    out = ai.call(db, "demo_script", system=SYSTEM, user=user, schema=SCRIPT_SCHEMA, user_id=job.created_by,
                  ref_type="demo_project", ref_id=p.id, job_id=job.id)
    labels = {h.id: (h.label or "verified") for h in comp_hits}
    for uc in out["use_cases"]:
        src = uc.get("differentiator_source", "")
        uc["differentiator_label"] = labels.get(src, "unsourced") if uc.get("differentiator") else ""
    flags = verify_steps(out, library, " ".join(h.text for h in doc_hits))
    n = (db.scalar(select(func.max(DemoScriptVersion.version)).where(DemoScriptVersion.project_id == p.id)) or 0) + 1
    db.add(DemoScriptVersion(project_id=p.id, version=n, content=out, unverified_steps=flags, saved_by=job.created_by))
    p.current_version = n
    db.commit()
    if job.created_by:
        notify(db, job.created_by, "demo", f"Demo script ready: {p.title}",
               f"{len(flags)} step(s) need manual validation." if flags else "", f"/demo/{p.id}")
    return {"version": n, "unverified": len(flags)}


def script_docx(title: str, content: dict, flags: list[dict]) -> bytes:
    doc = brand.new_document(f"Demo script - {title}")
    flagged = {(f["use_case"], f["step"]) for f in flags}
    o = content.get("opening", {})
    doc.add_heading("Opening", level=1)
    doc.add_paragraph(o.get("customer_context", ""))
    for ch in o.get("challenges", []):
        doc.add_paragraph(ch, style="List Bullet")
    e = content.get("end_result_first", {})
    doc.add_heading("The end result first", level=1)
    doc.add_paragraph(e.get("outcome", ""))
    doc.add_paragraph(e.get("how_to_show", ""))
    doc.add_heading("Agenda", level=1)
    brand.add_table(doc, ["Use case", "Pain point", "Minutes"], [[a["title"], a["pain"], a["minutes"]] for a in content.get("agenda", [])])
    for i, uc in enumerate(content.get("use_cases", [])):
        doc.add_heading(uc["title"], level=1)
        doc.add_paragraph(f"Pain: {uc['pain']}")
        doc.add_heading("Navigation and screens", level=3)
        for j, step in enumerate(uc.get("navigation", [])):
            doc.add_paragraph(step + ("  [VALIDATE]" if (i, j) in flagged else ""), style="List Number")
        doc.add_paragraph(f"Show: {uc['what_to_show']}")
        doc.add_paragraph(f"Value: {uc['value_statement']}")
        if uc.get("differentiator"):
            doc.add_paragraph(f"Differentiator ({uc.get('differentiator_label', '')}): {uc['differentiator']}")
        doc.add_paragraph(f"Check-in: {uc['check_in_question']}")
        if uc.get("transition"):
            doc.add_paragraph(f"Transition: {uc['transition']}")
    if content.get("objections"):
        doc.add_heading("Likely objections", level=1)
        brand.add_table(doc, ["Objection", "Suggested answer"], [[x["objection"], x["answer"]] for x in content["objections"]])
    c = content.get("closing", {})
    doc.add_heading("Closing and next steps", level=1)
    doc.add_paragraph(c.get("summary", ""))
    for s in c.get("next_steps", []):
        doc.add_paragraph(s, style="List Bullet")
    doc.add_heading("Pre-demo checklist", level=1)
    for s in content.get("checklist", []):
        doc.add_paragraph(s, style="List Bullet")
    return brand.document_bytes(doc)
