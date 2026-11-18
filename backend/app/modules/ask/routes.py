from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import client as ai
from app.ai import retrieval
from app.core.audit import audit
from app.core.deps import CurrentUser, require
from app.db import get_db
from app.models.knowledge import AnswerFeedback, ChatConversation, ChatMessage, QuestionGap, SizingRule
from app.modules.ask.sizing import apply_rules, render, required_inputs

router = APIRouter(prefix="/ask", tags=["ask"])

CLASSIFICATIONS = ["Supported", "Partially Supported", "Supported Through Integration/Configuration",
                   "Planned, Officially Confirmed", "Not Supported", "Not Verified", "Not applicable"]

ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["not_found", "direct_answer", "explanation", "product", "module", "classification", "citations",
                 "limitations", "clarification_needed", "conflicts", "sizing"],
    "properties": {
        "not_found": {"type": "boolean", "description": "true when the sources do not support an answer"},
        "direct_answer": {"type": "string"},
        "explanation": {"type": "string", "description": "technical explanation in Markdown"},
        "product": {"type": "string", "description": "ObserveOps, ServiceOps, Both or empty"},
        "module": {"type": "string"},
        "classification": {"type": "string", "enum": CLASSIFICATIONS},
        "citations": {"type": "array", "items": {"type": "string"}, "description": "source ids used, e.g. S1"},
        "limitations": {"type": "string"},
        "clarification_needed": {"type": "string"},
        "conflicts": {"type": "string", "description": "describe disagreeing sources, or empty"},
        "sizing": {
            "type": "object", "additionalProperties": False, "required": ["is_sizing_question", "product", "inputs"],
            "properties": {
                "is_sizing_question": {"type": "boolean"},
                "product": {"type": "string"},
                "inputs": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                      "required": ["name", "value"],
                                                      "properties": {"name": {"type": "string"}, "value": {"type": "number"}}}},
            },
        },
    },
}

SYSTEM = """You are Ask Motadata, an assistant for the presales team.
Answer only from the approved sources supplied. Give the direct answer first, then the technical explanation.
Name the product and module. Cite source ids (S1, S2...) in the citations list and inline as [S1].
Classify capability questions using exactly one classification. When the sources do not support an answer, set not_found to true and say "Not found in the approved documentation." Do not fall back to general knowledge.
If sources disagree, describe the conflict instead of choosing silently; current documentation outranks internal notes and past RFP answers.
Sizing questions (hardware, CPU, RAM, disk, number of servers): never state figures yourself. Set sizing.is_sizing_question to true and extract the numeric inputs the user gave, using these input names where they fit: {sizing_inputs}."""


class AskIn(BaseModel):
    question: str
    conversation_id: int | None = None
    product: str | None = None


def _conversation(db: Session, cu: CurrentUser, conv_id: int | None, question: str) -> ChatConversation:
    if conv_id:
        c = db.get(ChatConversation, conv_id)
        if not c or c.user_id != cu.id:
            raise HTTPException(404, "Conversation not found")
        return c
    c = ChatConversation(user_id=cu.id, title=question[:80])
    db.add(c)
    db.flush()
    return c


@router.post("")
def ask(body: AskIn, cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    if not body.question.strip():
        raise HTTPException(400, "Type a question")
    conv = _conversation(db, cu, body.conversation_id, body.question)
    history_rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
                              .order_by(ChatMessage.id.desc()).limit(6)).all()[::-1]
    history = [{"role": m.role, "content": m.content} for m in history_rows]
    db.add(ChatMessage(conversation_id=conv.id, role="user", content=body.question))
    db.commit()

    retrieval_query = body.question if not history else f"{history[-1]['content'][:300]}\n{body.question}"
    hits = retrieval.search(db, retrieval_query, cu.section_keys(), product=body.product)
    sizing_names = required_inputs(list(db.scalars(select(SizingRule).where(SizingRule.active.is_(True))))) or ["(none configured)"]
    user = f"<sources>\n{retrieval.format_hits(hits)}\n</sources>\n\nQuestion: {body.question}"
    try:
        out = ai.call(db, "ask_motadata", system=SYSTEM.format(sizing_inputs=", ".join(sizing_names)), user=user,
                      schema=ANSWER_SCHEMA, history=history, user_id=cu.id, ref_type="conversation", ref_id=conv.id)
    except ai.AIError as e:
        raise HTTPException(502, str(e)) from e

    hit_by_id = {h.id: h for h in hits}
    meta: dict = {k: out[k] for k in ("product", "module", "classification", "limitations", "clarification_needed", "conflicts")}
    if out["sizing"]["is_sizing_question"]:
        product = out["sizing"]["product"] or body.product or "ObserveOps"
        res = apply_rules(db, product, {i["name"]: i["value"] for i in out["sizing"]["inputs"]})
        content = render(res)
        meta["sizing"] = {"status": res.status, "inputs": res.inputs, "rows": res.rows, "missing": res.missing}
        citations = []
        not_found = False
    else:
        not_found = out["not_found"] or not hits
        if not_found:
            content = "Not found in the approved documentation."
            if out["direct_answer"] and hits:
                content += f"\n\n{out['direct_answer']}"
        else:
            content = f"{out['direct_answer']}\n\n{out['explanation']}".strip()
        citations = [hit_by_id[c].citation() for c in out["citations"] if c in hit_by_id]
    meta["not_found"] = not_found
    msg = ChatMessage(conversation_id=conv.id, role="assistant", content=content, citations=citations, meta=meta)
    db.add(msg)
    db.flush()
    if not_found:
        db.add(QuestionGap(question=body.question, reason="not_found", message_id=msg.id, user_id=cu.id))
    db.commit()
    return {"conversation_id": conv.id, "message": _msg_out(msg)}


def _msg_out(m: ChatMessage) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "citations": m.citations, "meta": m.meta, "at": m.at}


@router.get("/conversations")
def conversations(cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatConversation).where(ChatConversation.user_id == cu.id)
                      .order_by(ChatConversation.updated_at.desc()).limit(100)).all()
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in rows]


@router.get("/conversations/{cid}")
def conversation(cid: int, cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    c = db.get(ChatConversation, cid)
    if not c or c.user_id != cu.id:
        raise HTTPException(404, "Conversation not found")
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == cid).order_by(ChatMessage.id)).all()
    return {"id": c.id, "title": c.title, "messages": [_msg_out(m) for m in msgs]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    c = db.get(ChatConversation, cid)
    if not c or c.user_id != cu.id:
        raise HTTPException(404, "Conversation not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


class FeedbackIn(BaseModel):
    helpful: bool
    comment: str = ""


@router.post("/messages/{mid}/feedback")
def feedback(mid: int, body: FeedbackIn, cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    m = db.get(ChatMessage, mid)
    conv = db.get(ChatConversation, m.conversation_id) if m else None
    if not m or not conv or conv.user_id != cu.id:
        raise HTTPException(404, "Message not found")
    db.add(AnswerFeedback(message_id=mid, user_id=cu.id, helpful=body.helpful, comment=body.comment))
    if not body.helpful:
        q = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id == conv.id, ChatMessage.id < mid,
                                                ChatMessage.role == "user").order_by(ChatMessage.id.desc()))
        db.add(QuestionGap(question=q.content if q else "", reason="not_helpful", message_id=mid, user_id=cu.id,
                           comment=body.comment))
    db.commit()
    return {"ok": True}


@router.get("/gaps")
def gaps(resolved: bool = False, cu: CurrentUser = Depends(require("ask.view_gaps")), db: Session = Depends(get_db)):
    rows = db.scalars(select(QuestionGap).where(QuestionGap.resolved.is_(resolved)).order_by(QuestionGap.at.desc()).limit(500)).all()
    return [{"id": g.id, "question": g.question, "reason": g.reason, "comment": g.comment, "at": g.at, "resolved": g.resolved}
            for g in rows]


@router.post("/gaps/{gid}/resolve")
def resolve_gap(gid: int, cu: CurrentUser = Depends(require("ask.view_gaps")), db: Session = Depends(get_db)):
    g = db.get(QuestionGap, gid)
    if not g:
        raise HTTPException(404, "Not found")
    g.resolved = True
    db.commit()
    return {"ok": True}


# ---------- sizing rules (maintained by the Knowledge Administrator) ----------
class SizingRuleIn(BaseModel):
    product: str
    component: str
    conditions: dict[str, list[float | None]]
    result: dict[str, str | int | float]
    source: str = ""
    sort: int = 100
    active: bool = True


def _rule_out(r: SizingRule) -> dict:
    return {"id": r.id, "product": r.product, "component": r.component, "conditions": r.conditions, "result": r.result,
            "source": r.source, "sort": r.sort, "active": r.active}


@router.get("/sizing-rules")
def list_rules(cu: CurrentUser = Depends(require("ask.use", "knowledge.manage_sections")), db: Session = Depends(get_db)):
    return [_rule_out(r) for r in db.scalars(select(SizingRule).order_by(SizingRule.product, SizingRule.component, SizingRule.sort))]


@router.post("/sizing-rules")
def create_rule(body: SizingRuleIn, cu: CurrentUser = Depends(require("knowledge.manage_sections")), db: Session = Depends(get_db)):
    r = SizingRule(**body.model_dump())
    db.add(r)
    db.flush()
    audit(db, cu.user, "sizing.rule_created", "sizing_rule", r.id, **body.model_dump())
    db.commit()
    return _rule_out(r)


@router.put("/sizing-rules/{rid}")
def update_rule(rid: int, body: SizingRuleIn, cu: CurrentUser = Depends(require("knowledge.manage_sections")), db: Session = Depends(get_db)):
    r = db.get(SizingRule, rid)
    if not r:
        raise HTTPException(404, "Not found")
    before = _rule_out(r)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, cu.user, "sizing.rule_updated", "sizing_rule", r.id, before=before, after=body.model_dump())
    db.commit()
    return _rule_out(r)


@router.delete("/sizing-rules/{rid}")
def delete_rule(rid: int, cu: CurrentUser = Depends(require("knowledge.manage_sections")), db: Session = Depends(get_db)):
    r = db.get(SizingRule, rid)
    if not r:
        raise HTTPException(404, "Not found")
    audit(db, cu.user, "sizing.rule_deleted", "sizing_rule", r.id, before=_rule_out(r))
    db.delete(r)
    db.commit()
    return {"ok": True}


class SizingIn(BaseModel):
    product: str
    inputs: dict[str, float]


@router.post("/sizing")
def size(body: SizingIn, cu: CurrentUser = Depends(require("ask.use")), db: Session = Depends(get_db)):
    res = apply_rules(db, body.product, body.inputs)
    return {"status": res.status, "rows": res.rows, "missing": res.missing, "out_of_range": res.out_of_range,
            "text": render(res)}
