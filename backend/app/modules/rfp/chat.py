"""Chat about one RFP (database and AI side; see rfpchat.py for the pure parts).

Messages are RFPAgentRun rows "chat" (one per message, shared by the team working on the workspace), so no migration.
An assistant message can carry proposed changes ("actions"). A change to a review step is prepared by the existing
revision job and shown before / after; the team accepts or discards it, exactly as on the Bid workflow tab.
A change to bid parameters is previewed straight away and applied on Apply.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import client as ai
from app.ai import embeddings, retrieval
from app.models.core import Job
from app.models.rfp import RFPAgentRun, RFPComplianceResponse, RFPDocument, RFPRequirement, RFPWorkspace
from app.modules.rfp import rfpchat, stages
from app.modules.rfp import workflow as W

CHAT_KEY = "chat"
SEGMENTS, REQUIREMENTS, HISTORY = 14, 12, 6


def messages(db: Session, wid: int, limit: int = 200) -> list[RFPAgentRun]:
    rows = db.scalars(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == CHAT_KEY)
                      .order_by(RFPAgentRun.id.desc()).limit(limit)).all()
    return rows[::-1]


def message_out(db: Session, run: RFPAgentRun) -> dict:
    o = run.output
    actions = []
    for i, a in enumerate(o.get("actions") or []):
        a = {k: v for k, v in a.items() if k not in ("params", "sizing")}
        if a.get("state") == "preparing" and a.get("job_id"):
            job = db.get(Job, a["job_id"])
            draft = stages.latest(db, run.workspace_id, W.DRAFT_PREFIX + a["stage"])
            if job and job.status in ("Failed", "Cancelled"):
                a.update(state="failed", error=(job.error or job.status).split("\n")[0][:300])
            elif draft is not None and draft.job_id == a["job_id"]:
                a.update(state="ready", draft_id=draft.id, changes=_draft_changes(a["stage"], draft.output),
                         outdated=_outdated(db, run.workspace_id, a["stage"], draft))
            elif job and job.status == "Completed":
                a.update(state="closed")  # its draft was replaced, accepted or discarded on the step
        actions.append({**a, "index": i})
    return {"id": run.id, "role": o.get("role"), "content": o.get("content", ""), "citations": o.get("citations", []),
            "not_found": o.get("not_found", False), "actions": actions, "by": o.get("by", ""), "at": run.at}


def _draft_changes(stage: str, d: dict) -> list[dict]:
    if stage != "compliance":
        return d.get("changes") or []
    return [{"where": f"{a['number']} · {k.replace('_', ' ')}", "before": a["before"].get(k, ""), "after": a["after"].get(k, "")}
            for a in d.get("answers") or [] for k in ("status", "response", "explanation", "validation_remarks")
            if (a["before"].get(k) or "") != (a["after"].get(k) or "")]


def _outdated(db: Session, wid: int, stage: str, draft: RFPAgentRun) -> bool:
    if stage not in W.DOC_STAGES:
        return False
    run = stages.latest(db, wid, W.BY_KEY[stage]["agent"])
    return run is None or draft.output.get("base_run_id") != run.id


# ---------- context ----------
def _segments(db: Session, ws: RFPWorkspace, query: str) -> list[dict]:
    docs = db.scalars(select(RFPDocument).where(RFPDocument.workspace_id == ws.id,
                                                RFPDocument.role.in_(["rfp", "corrigendum"])).order_by(RFPDocument.id)).all()
    segs = [{"doc": d.name, "role": d.role, "revision": d.revision, **s} for d in docs for s in (d.extracted or [])]
    picked = rfpchat.rank(query, [f"{s.get('section', '')} {s.get('text', '')}" for s in segs], SEGMENTS)
    return [segs[i] for i in picked]


def _requirements(db: Session, ws: RFPWorkspace, query: str) -> list[tuple]:
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))
                      .order_by(RFPRequirement.id)).all()
    by_number = {r.number.upper(): (r, c) for r, c in rows}
    picked = [rows[i] for i in rfpchat.rank(query, [r.text for r, _ in rows], REQUIREMENTS)]
    for n in {t.upper() for t in rfpchat.tokens(query) if t[:1] == "r" and t[1:].isdigit()}:  # "R045" asked by number
        if n in by_number and by_number[n] not in picked:
            picked.insert(0, by_number[n])
    cfg = embeddings.active_config(db)
    if cfg:
        try:
            with db.begin_nested():  # an embedding model change can leave old vectors of another size
                vec = embeddings.embed_one(cfg, query, query=True)
                ids = db.scalars(select(RFPRequirement.id).where(RFPRequirement.workspace_id == ws.id,
                                                                RFPRequirement.active.is_(True),
                                                                RFPRequirement.embedding.is_not(None))
                                 .order_by(RFPRequirement.embedding.cosine_distance(vec)).limit(8)).all()
            have = {r.id for r, _ in picked}
            picked += [(r, c) for r, c in rows if r.id in set(ids) - have]
        except Exception:  # keyword matches are still there
            pass
    return picked[:REQUIREMENTS + 8]


def ask(db: Session, ws: RFPWorkspace, *, question: str, user_id: int, by: str, sections: set[str],
        runs: dict, params: dict) -> RFPAgentRun:
    """Answer a question or change request about this RFP. Stores the question and the answer; returns the answer row."""
    prior = messages(db, ws.id, HISTORY)
    history = [{"role": m.output["role"], "content": m.output.get("content", "")} for m in prior]
    last_q = next((m.output.get("content", "") for m in reversed(prior) if m.output.get("role") == "user"), "")
    query = f"{question}\n{last_q[:300]}"
    db.add(RFPAgentRun(workspace_id=ws.id, agent_key=CHAT_KEY, revision=ws.revision,
                       output={"role": "user", "content": question, "by": by}))
    db.commit()

    segs = _segments(db, ws, query)
    reqs = _requirements(db, ws, query)
    hits = retrieval.search(db, question, sections, top_k=5)
    past = retrieval.search_submitted(db, question, top_k=3)
    overview = stages.overview(db, ws)
    material = rfpchat.workspace_material(runs, params, overview["compliance"],
                                          {s["label"]: s["status"] for s in overview["stages"]})
    cites: dict[str, dict] = {}
    parts = []
    for i, s in enumerate(segs, start=1):
        cid = f"D{i}"
        cites[cid] = {"id": cid, "kind": "rfp", "label": s["doc"], "ref": s.get("ref", ""), "text": s.get("text", "")[:400]}
        parts.append(f'<passage id="{cid}" document="{s["doc"]}" ref="{s.get("ref", "")}" section="{s.get("section", "")}"'
                     f'{" corrigendum" if s["role"] == "corrigendum" else ""}>{s.get("text", "")[:3000]}</passage>')
    for i, (r, c) in enumerate(reqs, start=1):
        cid = f"R{i}"
        cites[cid] = {"id": cid, "kind": "requirement", "label": r.number, "ref": f"{r.source_file} {r.source_ref}".strip(),
                      "text": r.text[:400]}
        ans = (f" | compliance: {c.status}{' (approved)' if c.approved else ''} | response: {c.response[:400]}"
               f"{' | remarks: ' + c.validation_remarks[:200] if c.validation_remarks else ''}") if c else " | not answered"
        parts.append(f'<requirement id="{cid}" number="{r.number}" ref="{r.source_file} {r.source_ref}">'
                     f"{r.text[:1500]}{ans}</requirement>")
    for h in hits:
        cites[h.id] = {**h.citation(), "kind": "knowledge"}
    for p in past:
        cites[p.id] = {"id": p.id, "kind": "past", "label": f"{p.customer} {p.submitted_on} v{p.product_version}".strip(),
                       "ref": p.status, "text": p.requirement[:400]}
    past_txt = "\n".join(f'<past id="{p.id}" customer="{p.customer}" date="{p.submitted_on}">Requirement: {p.requirement}\n'
                         f"Status: {p.status}\nResponse: {p.response}</past>" for p in past)
    user = (f"<rfp>\n{chr(10).join(parts) or '(no matching passages)'}\n</rfp>\n<working_outputs>\n{material}\n"
            f"</working_outputs>\n<knowledge>\n{retrieval.format_hits(hits)}\n</knowledge>\n<past_bids>\n"
            f"{past_txt or '(none)'}\n</past_bids>\n\nQuestion: {question}")
    out = ai.call(db, "rfp_analysis", system=rfpchat.system_prompt(), user=user, schema=rfpchat.CHAT_SCHEMA,
                  history=history, user_id=user_id, ref_type="rfp_workspace", ref_id=ws.id)
    numbers = dict(db.execute(select(RFPRequirement.number, RFPRequirement.id)
                              .where(RFPRequirement.workspace_id == ws.id, RFPRequirement.active.is_(True))).all())
    actions = rfpchat.check_actions(out["actions"], {n.upper(): i for n, i in numbers.items()}, params)
    run = RFPAgentRun(workspace_id=ws.id, agent_key=CHAT_KEY, revision=ws.revision, output={
        "role": "assistant", "content": out["answer"], "not_found": out["not_found"],
        "citations": [cites[c] for c in dict.fromkeys(out["citations"]) if c in cites], "actions": actions})
    db.add(run)
    db.flush()
    return run


def set_action(run: RFPAgentRun, index: int, **values) -> dict:
    actions = [dict(a) for a in run.output.get("actions") or []]
    actions[index].update(values)
    run.output = {**run.output, "actions": actions}  # a new dict, so the JSONB change is saved
    return actions[index]


def close_by_job(db: Session, wid: int, job_id: int | None, state: str) -> None:
    """A draft made for a chat action was accepted or discarded on the step: show that on the chat card."""
    if not job_id:
        return
    for m in messages(db, wid, 60):
        for i, a in enumerate(m.output.get("actions") or []):
            if a.get("job_id") == job_id:
                set_action(m, i, state=state)
