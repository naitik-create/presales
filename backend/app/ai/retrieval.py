"""Permission-filtered retrieval over the Knowledge Hub (§6.3, §12). Filtering happens before any text reaches Claude."""
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import embeddings
from app.models.knowledge import (DocumentChunk, DocumentVersion, KnowledgeSection, KnowledgeSource,
                                  SubmittedRequirementResponse, SubmittedRFP)


@dataclass
class Hit:
    id: str  # citation id shown to the model, e.g. "S12"
    chunk_id: int
    source_id: int
    title: str
    section: str
    section_key: str
    section_path: str
    page: str
    url: str
    product: str
    product_version: str
    priority: int
    label: str
    text: str
    score: float

    def citation(self) -> dict:
        return {"id": self.id, "source_id": self.source_id, "title": self.title, "section": self.section,
                "section_path": self.section_path, "page": self.page, "url": self.url,
                "product_version": self.product_version, "label": self.label}


def search(db: Session, query: str, allowed_sections: set[str], *, top_k: int = 8, sections: list[str] | None = None,
           product: str | None = None, id_prefix: str = "S") -> list[Hit]:
    keys = set(allowed_sections)
    if sections:
        keys &= set(sections)
    if not keys or not query.strip():
        return []
    cfg = embeddings.active_config(db)
    q = (select(DocumentChunk, KnowledgeSource, KnowledgeSection)
         .join(KnowledgeSource, KnowledgeSource.id == DocumentChunk.source_id)
         .join(KnowledgeSection, KnowledgeSection.id == DocumentChunk.section_id)
         .where(KnowledgeSource.status == "Approved", KnowledgeSection.enabled.is_(True),
                KnowledgeSection.key.in_(keys)))
    # only chunks of the source's current version
    q = q.join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id).where(
        DocumentVersion.version == KnowledgeSource.current_version)
    if product and product != "Both":
        q = q.where(KnowledgeSource.product.in_([product, "Both"]))

    rows = []
    if cfg is not None:
        vec = embeddings.embed_one(cfg, query, query=True)
        dist = DocumentChunk.embedding.cosine_distance(vec)
        rows = db.execute(q.where(DocumentChunk.embedding_model == cfg.model_name)
                          .add_columns(dist.label("dist")).order_by(dist).limit(top_k * 3)).all()
        scored = [(r[0], r[1], r[2], 1 - float(r[3])) for r in rows]
    else:
        ts = func.plainto_tsquery("english", query)
        rank = func.ts_rank(func.to_tsvector("english", DocumentChunk.text), ts)
        rows = db.execute(q.where(func.to_tsvector("english", DocumentChunk.text).op("@@")(ts))
                          .add_columns(rank.label("rank")).order_by(rank.desc()).limit(top_k * 3)).all()
        scored = [(r[0], r[1], r[2], float(r[3])) for r in rows]

    # Prefer current documentation over internal knowledge and past submissions (§6.5)
    scored.sort(key=lambda t: t[3] - 0.04 * (t[2].priority - 1), reverse=True)
    hits = []
    for i, (ch, src, sec, score) in enumerate(scored[:top_k], start=1):
        hits.append(Hit(id=f"{id_prefix}{i}", chunk_id=ch.id, source_id=src.id, title=src.title, section=sec.name,
                        section_key=sec.key, section_path=ch.section_path, page=ch.page, url=src.url,
                        product=src.product, product_version=src.product_version, priority=sec.priority,
                        label=src.label, text=ch.text, score=round(score, 4)))
    return hits


@dataclass
class PastAnswer:
    id: str
    pair_id: int
    customer: str
    submitted_on: str
    product_version: str
    requirement: str
    status: str
    response: str
    score: float


def search_submitted(db: Session, query: str, *, top_k: int = 4, exclude_held_back: bool = True) -> list[PastAnswer]:
    cfg = embeddings.active_config(db)
    if cfg is None:
        return []
    vec = embeddings.embed_one(cfg, query, query=True)
    dist = SubmittedRequirementResponse.embedding.cosine_distance(vec)
    q = (select(SubmittedRequirementResponse, SubmittedRFP, dist.label("d"))
         .join(SubmittedRFP, SubmittedRFP.id == SubmittedRequirementResponse.submitted_rfp_id)
         .where(SubmittedRequirementResponse.embedding_model == cfg.model_name))
    if exclude_held_back:
        q = q.where(SubmittedRFP.held_back_for_testing.is_(False))
    rows = db.execute(q.order_by(dist).limit(top_k)).all()
    return [PastAnswer(id=f"P{i}", pair_id=p.id, customer=r.customer,
                       submitted_on=r.submitted_on.isoformat() if r.submitted_on else "",
                       product_version=r.product_version, requirement=p.requirement, status=p.status,
                       response=p.response, score=round(1 - float(d), 4))
            for i, (p, r, d) in enumerate(rows, start=1)]


def format_hits(hits: list[Hit]) -> str:
    from app.ai.client import doc_block
    return "\n\n".join(
        doc_block(h.id, h.title, h.text, f"{h.section} | {h.section_path} | {h.page} | version {h.product_version or 'n/a'}"
                  + (f" | {h.label}" if h.label else ""))
        for h in hits) or "(no approved sources matched)"

