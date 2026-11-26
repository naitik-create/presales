"""RFP processing pipeline (§8.3-8.9). Runs in the 'rfp' queue so concurrency and queue limits apply."""
from difflib import SequenceMatcher

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai import client as ai
from app.ai import embeddings, retrieval
from app.core.jobs import ON_END, JobContext, handler
from app.core.notify import notify
from app.core.storage import read_file
from app.models.ai import AIUsageLog
from app.models.core import Job, StoredFile
from app.models.knowledge import KnowledgeSection, SizingRule
from app.models.rfp import RFPAgentRun, RFPComplianceResponse, RFPDocument, RFPRequirement, RFPWorkspace
from app.modules.ask.sizing import apply_rules, required_inputs
from app.modules.rfp import agents as A
from app.modules.rfp import bidpack
from app.common.text import normalise
from app.parsing.extract import extract

WINDOW_CHARS = 40_000  # requirement extraction works section by section in windows of this size
DOC_AGENT_LIMIT = 600_000  # above this the document-level agents run per window and results are merged
RFP_SECTIONS = ["specifications", "datasheets", "prerequisites", "architecture_and_deployment", "integrations",
                "licensing", "online_documentation", "hardware_requirements_and_sizing"]


def workspace_cost(db: Session, wid: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(AIUsageLog.estimated_cost), 0))
                           .where(AIUsageLog.ref_type == "rfp_workspace", AIUsageLog.ref_id == wid)) or 0)


def _lines(doc: RFPDocument) -> list[str]:
    return [f"[{s['ref']}] {('(' + s['section'] + ') ') if s.get('section') else ''}{s['text']}" for s in doc.extracted]


def windows(docs: list[RFPDocument]) -> list[tuple[str, str]]:
    """[(file name, window text)] keeping lines whole and in order."""
    out = []
    for d in docs:
        buf, size = [], 0
        for line in _lines(d):
            if buf and size + len(line) > WINDOW_CHARS:
                out.append((d.name, "\n".join(buf)))
                buf, size = [], 0
            buf.append(line)
            size += len(line) + 1
        if buf:
            out.append((d.name, "\n".join(buf)))
    return out


def extract_documents(db: Session, ws: RFPWorkspace, ctx: JobContext, role: str = "rfp") -> list[RFPDocument]:
    docs = list(db.scalars(select(RFPDocument).where(RFPDocument.workspace_id == ws.id, RFPDocument.role == role,
                                                    RFPDocument.revision == ws.revision)))
    for i, d in enumerate(docs):
        if d.status == "Extracted":
            continue
        f = db.get(StoredFile, d.file_id)
        ex = extract(read_file(f), f.original_name)
        d.extracted = [{"ref": s.ref, "section": s.section, "text": s.text, "file": s.file or d.name} for s in ex.segments]
        d.used_ocr, d.status = ex.used_ocr, "Extracted"
        db.commit()
        ctx.progress(5 + int(10 * (i + 1) / max(1, len(docs))), f"Extracted {d.name}")
    return docs


def extract_requirements(db: Session, ws: RFPWorkspace, docs: list[RFPDocument], ctx: JobContext, job: Job) -> list[dict]:
    reqs: list[dict] = []
    wins = windows(docs)
    for i, (fname, text) in enumerate(wins):
        out = ai.call(db, "requirement_extraction", system=A.EXTRACT_SYSTEM,
                      user=f'<document name="{fname}">\n{text}\n</document>', schema=A.EXTRACT_SCHEMA,
                      user_id=job.created_by, ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
        for r in out["requirements"]:
            if r["text"].strip():
                reqs.append({**r, "file": fname})
        ctx.progress(15 + int(25 * (i + 1) / max(1, len(wins))), f"Identified requirements in part {i + 1} of {len(wins)}")
    return reqs


def _evidence_for(db: Session, req: RFPRequirement, prefix: str):
    allowed = set(db.scalars(select(KnowledgeSection.key)))
    hits = retrieval.search(db, req.text, allowed, sections=RFP_SECTIONS, top_k=5, id_prefix=f"{prefix}S")
    past = retrieval.search_submitted(db, req.text, top_k=3)
    for p in past:
        p.id = f"{prefix}{p.id}"
    return hits, past


def run_compliance(db: Session, ws: RFPWorkspace, reqs: list[RFPRequirement], ctx: JobContext, job: Job,
                   start_pct: int = 45, end_pct: int = 85) -> None:
    todo = list(reqs)
    for i in range(0, len(todo), 6):
        batch = todo[i:i + 6]
        parts, lookup = [], {}
        for r in batch:
            prefix = f"R{r.id}-"
            hits, past = _evidence_for(db, r, prefix)
            lookup[str(r.id)] = (hits, past)
            p = "\n".join(f'<source id="{x.id}" title="Past answer: {x.customer} {x.submitted_on} v{x.product_version}">'
                          f"Requirement: {x.requirement}\nStatus: {x.status}\nResponse: {x.response}</source>" for x in past)
            parts.append(f'<requirement id="{r.id}" ref="{r.source_file} {r.source_ref}">{r.text}</requirement>\n'
                         f"<sources>\n{retrieval.format_hits(hits)}\n{p}\n</sources>")
        out = ai.call(db, "technical_compliance", system=A.COMPLIANCE_SYSTEM, user="\n\n".join(parts),
                      schema=A.COMPLIANCE_SCHEMA, user_id=job.created_by, ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
        by_id = {str(r.id): r for r in batch}
        for a in out["answers"]:
            r = by_id.get(a["requirement_id"])
            if not r:
                continue
            hits, past = lookup[str(r.id)]
            cites = [h.citation() for h in hits if h.id in a["source_ids"]]
            reused = [x for x in past if x.id in a["source_ids"]]
            cites += [{"id": x.id, "kind": "submitted_rfp", "customer": x.customer, "submitted_on": x.submitted_on,
                       "product_version": x.product_version, "pair_id": x.pair_id} for x in reused]
            origin = "submitted_rfp" if reused and not any(h.id in a["source_ids"] for h in hits) else "ai"
            _upsert_response(db, r, {"status": a["status"], "response": a["proposed_response"], "explanation": a["explanation"],
                                     "evidence": a["evidence"], "sources": cites, "validation_remarks": a["validation_remarks"],
                                     "origin": origin,
                                     "origin_detail": {"reused_from": [{"customer": x.customer, "date": x.submitted_on,
                                                                        "product_version": x.product_version} for x in reused]}})
        db.commit()
        ctx.progress(start_pct + int((end_pct - start_pct) * min(1, (i + 6) / max(1, len(todo)))),
                     f"Compliance answers: {min(i + 6, len(todo))} of {len(todo)}")

def _upsert_response(db: Session, r: RFPRequirement, values: dict) -> None:
    resp = db.scalar(select(RFPComplianceResponse).where(RFPComplianceResponse.requirement_id == r.id))
    if resp is None:
        resp = RFPComplianceResponse(requirement_id=r.id)
        db.add(resp)
    elif resp.approved:
        return  # never overwrite an approved answer
    for k, v in values.items():
        setattr(resp, k, v)


def full_text(db: Session, ws: RFPWorkspace) -> list[str]:
    docs = db.scalars(select(RFPDocument).where(RFPDocument.workspace_id == ws.id, RFPDocument.role.in_(["rfp", "corrigendum"]))
                      .order_by(RFPDocument.id)).all()
    text = "\n\n".join(f'<document name="{d.name}">\n' + "\n".join(_lines(d)) + "\n</document>" for d in docs)
    if len(text) <= DOC_AGENT_LIMIT:
        return [text]
    return [f'<document name="{n}">\n{t}\n</document>' for n, t in windows(list(docs))]


def compliance_digest(db: Session, ws: RFPWorkspace) -> str:
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))
                      .order_by(RFPRequirement.id)).all()
    return "\n".join(f"{r.number} [{r.source_ref}] {r.text[:300]} => {c.status if c else 'pending'}"
                     + (f" ({c.validation_remarks[:150]})" if c and c.validation_remarks else "") for r, c in rows)


SCOPE_BATCH = 150  # requirements per scope call, so the matrix fits the output limit
SCOPE_SECTIONS = ["internal_presales_knowledge", "licensing", "datasheets", "specifications", "online_documentation"]


def run_scope(db: Session, ws: RFPWorkspace, job: Job) -> dict:
    """Owner and module for every active requirement, plus the scope summary. Works from the requirement list and
    compliance answers rather than the full RFP text, in batches."""
    agent_key, schema, system, _ = A.DOC_AGENTS["scope"]
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))
                      .order_by(RFPRequirement.id)).all()
    allowed = set(db.scalars(select(KnowledgeSection.key)))
    hits = retrieval.search(db, "Motadata modules product scope standard exclusions deviations partner responsibilities "
                                "what the partner supplies", allowed, sections=SCOPE_SECTIONS, top_k=10)
    knowledge = f"<knowledge>\n{retrieval.format_hits(hits)}\n</knowledge>"
    merged: dict = {}
    for i in range(0, len(rows), SCOPE_BATCH):
        listing = "\n".join(f"{r.number} | {r.category} | {r.source_file} {r.source_ref} | {' '.join(r.text.split())[:500]}"
                            f" | {c.status if c else 'pending'}" for r, c in rows[i:i + SCOPE_BATCH])
        out = ai.call(db, agent_key, system=system, user=f'<document name="requirements">\n{listing}\n</document>\n{knowledge}',
                      schema=schema, user_id=job.created_by, ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
        bidpack.merge_outputs(merged, out)
    bidpack.finalise_scope(merged, [r.number for r, _ in rows])
    merged["citations"] = [h.citation() for h in hits]
    return merged


def run_doc_agent(db: Session, ws: RFPWorkspace, key: str, job: Job) -> dict:
    if key == "scope":
        return run_scope(db, ws, job)
    agent_key, schema, system, uses_kb = A.DOC_AGENTS[key]
    parts = full_text(db, ws)
    extra = ""
    if key in ("risk", "synopsis", "pqtq", "prebid", "boq"):
        extra += f"\n<compliance_answers>\n{compliance_digest(db, ws)}\n</compliance_answers>"
    hits = []
    if uses_kb:
        allowed = set(db.scalars(select(KnowledgeSection.key)))
        q = {"architecture": "deployment architecture high availability prerequisites sizing",
             "pqtq": "certifications OEM support experience", "boq": "licensing model licence metrics modules"}[key]
        hits = retrieval.search(db, q, allowed, top_k=8)
        extra += f"\n<knowledge>\n{retrieval.format_hits(hits)}\n</knowledge>"
    sys = system
    if key == "architecture":
        names = required_inputs(list(db.scalars(select(SizingRule).where(SizingRule.active.is_(True)))))
        sys += f"\nSizing input names: {', '.join(names) or '(none configured)'}."
    merged: dict = {}
    for part in parts:
        out = ai.call(db, agent_key, system=sys, user=part + extra, schema=schema, user_id=job.created_by,
                      ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
        bidpack.merge_outputs(merged, out)
    if key == "analysis":
        bidpack.finalise_analysis(merged)
    if key == "prebid":
        bidpack.finalise_prebid(merged)
    if key == "architecture":
        inputs = {i["name"]: i["value"] for i in merged.get("sizing_inputs", [])}
        products = ws.products or ["ObserveOps"]
        merged["sizing"] = [{"product": p, **_sizing(db, p, inputs)} for p in products]
        merged["citations"] = [h.citation() for h in hits if h.id in merged.get("source_ids", [])]
    return merged


def _sizing(db: Session, product: str, inputs: dict) -> dict:
    res = apply_rules(db, product, inputs)
    return {"status": res.status, "rows": res.rows, "missing": res.missing, "out_of_range": res.out_of_range}


def store_agent_run(db: Session, ws: RFPWorkspace, key: str, output: dict, job: Job) -> None:
    db.add(RFPAgentRun(workspace_id=ws.id, agent_key=key, revision=ws.revision, output=output, job_id=job.id))


def renumber(db: Session, ws: RFPWorkspace) -> None:
    for i, r in enumerate(db.scalars(select(RFPRequirement).where(RFPRequirement.workspace_id == ws.id)
                                     .order_by(RFPRequirement.id)), start=1):
        if not r.number:
            r.number = f"R{i:03d}"


def embed_requirements(db: Session, reqs: list[RFPRequirement]) -> None:
    cfg = embeddings.active_config(db)
    if not cfg:
        return
    for i in range(0, len(reqs), 64):
        batch = reqs[i:i + 64]
        for r, v in zip(batch, embeddings.embed(cfg, [r.text for r in batch])):
            r.embedding = v


@handler("rfp.process")
def process(db: Session, job: Job, ctx: JobContext) -> dict:
    ws = db.get(RFPWorkspace, job.payload["workspace_id"])
    ws.status = "Processing"
    db.commit()
    docs = extract_documents(db, ws, ctx)
    found = extract_requirements(db, ws, docs, ctx, job)
    db.execute(delete(RFPRequirement).where(RFPRequirement.workspace_id == ws.id, RFPRequirement.revision == ws.revision))
    new = []
    for i, r in enumerate(found, start=1):
        req = RFPRequirement(workspace_id=ws.id, number=f"R{i:03d}", text=r["text"], category=r["category"],
                             source_file=r["file"], source_ref=r["ref"], revision=ws.revision)
        db.add(req)
        new.append(req)
    db.flush()
    embed_requirements(db, new)
    db.commit()
    ctx.progress(42, f"{len(new)} requirements identified")
    run_compliance(db, ws, new, ctx, job)
    for i, key in enumerate(["analysis", "scope", "architecture", "risk", "pqtq", "boq", "synopsis", "prebid"]):
        ctx.progress(85 + i * 2, f"Running {A.DOC_AGENT_LABELS[key]}")
        store_agent_run(db, ws, key, run_doc_agent(db, ws, key, job), job)
        db.commit()
    ws.status = "Awaiting Review"
    db.commit()
    if job.created_by:
        notify(db, job.created_by, "rfp_done", f"RFP analysis ready: {ws.name}",
               f"{len(new)} requirements. Estimated cost {workspace_cost(db, ws.id):.2f}.", f"/rfp/{ws.id}")
    return {"requirements": len(new)}


@handler("rfp.agent")
def rerun_agent(db: Session, job: Job, ctx: JobContext) -> dict:
    ws = db.get(RFPWorkspace, job.payload["workspace_id"])
    key = job.payload["agent"]
    if key == "compliance":
        ids = job.payload.get("requirement_ids")
        q = select(RFPRequirement).where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))
        if ids:
            q = q.where(RFPRequirement.id.in_(ids))
        run_compliance(db, ws, list(db.scalars(q)), ctx, job, 5, 95)
    else:
        store_agent_run(db, ws, key, run_doc_agent(db, ws, key, job), job)
    db.commit()
    return {"agent": key}


@handler("rfp.corrigendum")
def corrigendum(db: Session, job: Job, ctx: JobContext) -> dict:
    """Show added, changed and removed requirements; keep approved answers for unchanged ones; re-run agents only for changes."""
    ws = db.get(RFPWorkspace, job.payload["workspace_id"])
    mode = job.payload.get("mode", "corrigendum")
    ws.status = "Processing"
    db.commit()
    role = "rfp" if mode == "revised" else "corrigendum"
    docs = extract_documents(db, ws, ctx, role=role)
    existing = list(db.scalars(select(RFPRequirement).where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))))
    changed_reqs: list[RFPRequirement] = []
    next_no = (db.scalar(select(func.count()).select_from(RFPRequirement).where(RFPRequirement.workspace_id == ws.id)) or 0) + 1
    for r in existing:
        r.change = ""
    if mode == "revised":
        found = extract_requirements(db, ws, docs, ctx, job)
        unmatched = {r.id: r for r in existing}
        for f in found:
            nf = normalise(f["text"])
            best, score = None, 0.0
            for r in unmatched.values():
                s = SequenceMatcher(None, nf, normalise(r.text)).ratio()
                if s > score:
                    best, score = r, s
            if best and score >= 0.97:
                unmatched.pop(best.id)
                best.source_ref, best.revision = f["ref"], ws.revision
            elif best and score >= 0.75:
                unmatched.pop(best.id)
                best.text, best.change, best.source_ref, best.revision = f["text"], "changed", f["ref"], ws.revision
                changed_reqs.append(best)
            else:
                nr = RFPRequirement(workspace_id=ws.id, number=f"R{next_no:03d}", text=f["text"], category=f["category"],
                                    source_file=f["file"], source_ref=f["ref"], revision=ws.revision, change="added")
                next_no += 1
                db.add(nr)
                changed_reqs.append(nr)
        for r in unmatched.values():
            r.change, r.active = "removed", False
    else:
        listing = "\n".join(f"{r.number}: {r.text[:400]}" for r in existing)
        by_no = {r.number: r for r in existing}
        for fname, text in windows(docs):
            out = ai.call(db, "requirement_extraction", system=A.CORRIGENDUM_SYSTEM,
                          user=f"<requirements>\n{listing}\n</requirements>\n<document name=\"{fname}\">\n{text}\n</document>",
                          schema=A.CORRIGENDUM_SCHEMA, user_id=job.created_by, ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
            for ch in out["changes"]:
                target = by_no.get(ch["original_number"])
                if ch["action"] == "added":
                    nr = RFPRequirement(workspace_id=ws.id, number=f"R{next_no:03d}", text=ch["text"], category=ch["category"] or "Technical",
                                        source_file=fname, source_ref=ch["ref"], revision=ws.revision, change="added")
                    next_no += 1
                    db.add(nr)
                    changed_reqs.append(nr)
                elif target and ch["action"] == "changed":
                    target.text, target.change, target.source_ref, target.revision = ch["text"], "changed", ch["ref"], ws.revision
                    changed_reqs.append(target)
                elif target and ch["action"] == "removed":
                    target.change, target.active = "removed", False
    db.flush()
    for r in changed_reqs:
        resp = db.scalar(select(RFPComplianceResponse).where(RFPComplianceResponse.requirement_id == r.id))
        if resp:
            resp.approved = False  # the requirement changed, so its answer needs review again
    embed_requirements(db, changed_reqs)
    db.commit()
    run_compliance(db, ws, changed_reqs, ctx, job, 50, 85)
    for key in ("analysis", "scope", "risk", "synopsis", "prebid"):
        store_agent_run(db, ws, key, run_doc_agent(db, ws, key, job), job)
        db.commit()
    ws.status = "Awaiting Review"
    db.commit()
    if job.created_by:
        notify(db, job.created_by, "rfp_done", f"Corrigendum processed: {ws.name}", f"{len(changed_reqs)} requirements changed.", f"/rfp/{ws.id}")
    return {"changed": len(changed_reqs)}


def _rfp_failed(db: Session, job: Job, status: str) -> None:
    ws = db.get(RFPWorkspace, job.payload.get("workspace_id"))
    if ws:
        ws.status = "Failed" if status == "Failed" else "Cancelled"
        if job.created_by:
            notify(db, job.created_by, "rfp_failed", f"RFP job {status.lower()}: {ws.name}",
                   (job.error or "").split("\n")[0][:300], f"/rfp/{ws.id}")


for _k in ("rfp.process", "rfp.corrigendum", "rfp.agent"):
    ON_END[_k] = _rfp_failed
