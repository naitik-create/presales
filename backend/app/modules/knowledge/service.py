"""Knowledge Hub ingestion (§6.2-6.3) and re-indexing (§5.3)."""
import hashlib
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.ai import embeddings
from app.ai.client import log_usage
from app.core.jobs import ON_END, JobContext, handler
from app.core.notify import notify, notify_permission
from app.core.settings_store import get_setting
from app.core.storage import read_file
from app.db import utcnow
from app.models.ai import EmbeddingConfiguration
from app.models.core import Job, StoredFile
from app.models.knowledge import DocumentChunk, DocumentVersion, KnowledgeSection, KnowledgeSource
from app.parsing.chunk import chunk_segments
from app.parsing.extract import Extracted, extract, html_to_segments

USER_AGENT = "MotadataPresalesBot/1.0 (+internal)"


def domain_allowed(db: Session, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    allowed = [d.lower() for d in get_setting(db, "url_fetch_allowed_domains")]
    return any(host == d or host.endswith("." + d) for d in allowed)


def fetch_url(db: Session, url: str) -> tuple[bytes, Extracted]:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs can be registered")
    if not domain_allowed(db, url):
        raise ValueError("This domain is not on the allowed list (Administration > Settings)")
    r = httpx.get(url, timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    if not domain_allowed(db, str(r.url)):
        raise ValueError("The URL redirected to a domain that is not allowed")
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype:
        return r.content, extract(r.content, "page.pdf")
    return r.content, html_to_segments(r.text, url)


def embed_chunks(db: Session, cfg: EmbeddingConfiguration, version: DocumentVersion, source: KnowledgeSource,
                 texts_meta: list[tuple[str, str, str]], ctx: JobContext | None = None, user_id: int | None = None) -> int:
    """Create chunk rows for one version under one embedding model. texts_meta = [(text, section_path, page)]."""
    total = 0
    for i in range(0, len(texts_meta), 64):
        batch = texts_meta[i:i + 64]
        vecs = embeddings.embed(cfg, [t for t, _, _ in batch])
        for j, ((text, path, page), vec) in enumerate(zip(batch, vecs)):
            db.add(DocumentChunk(version_id=version.id, source_id=source.id, section_id=source.section_id,
                                 ordinal=i + j, text=text, section_path=path[:500], page=page[:40], embedding=vec,
                                 embedding_model=cfg.model_name, embedding_dim=cfg.dimension,
                                 meta={"product": source.product, "version": source.product_version,
                                       "document_type": source.document_type}))
        total += len(batch)
        if ctx:
            ctx.check()
    if cfg.provider == "external":
        log_usage(db, user_id=user_id, module="knowledge", agent_key="embedding", kind="embedding",
                  model_id=cfg.model_name, input_tokens=sum(len(t) for t, _, _ in texts_meta) // 4,
                  ref_type="knowledge_source", ref_id=source.id)
    return total


@handler("knowledge.ingest")
def ingest(db: Session, job: Job, ctx: JobContext) -> dict:
    version = db.get(DocumentVersion, job.payload["version_id"])
    source = db.get(KnowledgeSource, version.source_id)
    source.ingest_status = "Processing"
    db.commit()
    ctx.progress(5, "Extracting text")
    if source.kind == "url":
        source.last_fetch_attempt_at = utcnow()
        raw, ex = fetch_url(db, source.url)
        version.sha256 = hashlib.sha256(raw).hexdigest()
        source.last_fetch_ok_at = utcnow()
    else:
        f = db.get(StoredFile, version.file_id)
        ex = extract(read_file(f), f.original_name)
    version.used_ocr, version.page_count = ex.used_ocr, ex.page_count
    r = get_setting(db, "retrieval")
    chunks = chunk_segments(ex.segments, r["chunk_chars"], r["chunk_overlap"])
    if not chunks:
        raise ValueError("No text could be extracted from this source")
    ctx.progress(30, f"Embedding {len(chunks)} chunks")
    cfg = embeddings.active_config(db)
    if cfg is None:
        raise RuntimeError("No embedding model is active")
    db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
    n = embed_chunks(db, cfg, version, source, [(c.text, c.section_path, c.page) for c in chunks], ctx, job.created_by)
    # also embed under a model being re-indexed to, so the new index is complete when it switches
    pending = db.scalar(select(EmbeddingConfiguration).where(EmbeddingConfiguration.pending_activation.is_(True)))
    if pending and pending.id != cfg.id:
        embed_chunks(db, pending, version, source, [(c.text, c.section_path, c.page) for c in chunks], None, job.created_by)
    version.embedding_model = cfg.model_name
    source.current_version = version.version
    source.ingest_status = "Ready"
    source.ingest_error = ""
    db.commit()
    return {"chunks": n, "ocr": ex.used_ocr}


def _ingest_failed(db: Session, job: Job, status: str) -> None:
    version = db.get(DocumentVersion, job.payload.get("version_id"))
    if not version:
        return
    source = db.get(KnowledgeSource, version.source_id)
    source.ingest_status = "Failed"
    source.ingest_error = (job.error or status).split("\n")[0][:500]
    if source.kind == "url":
        source.last_fetch_attempt_at = utcnow()
    notify_permission(db, "knowledge.approve", "ingestion_failed", f"Ingestion failed: {source.title}",
                      source.ingest_error, f"/knowledge?source={source.id}")


ON_END["knowledge.ingest"] = _ingest_failed


@handler("knowledge.reindex")
def reindex(db: Session, job: Job, ctx: JobContext) -> dict:
    """Build a complete index under the new model, then switch. Search uses the old index until the switch."""
    target = db.get(EmbeddingConfiguration, job.payload["config_id"])
    rows = db.execute(select(DocumentVersion, KnowledgeSource)
                      .join(KnowledgeSource, KnowledgeSource.id == DocumentVersion.source_id)
                      .where(DocumentVersion.version == KnowledgeSource.current_version)).all()
    total = len(rows) or 1
    for i, (version, source) in enumerate(rows):
        old = db.execute(select(DocumentChunk.text, DocumentChunk.section_path, DocumentChunk.page)
                         .where(DocumentChunk.version_id == version.id, DocumentChunk.embedding_model != target.model_name)
                         .order_by(DocumentChunk.ordinal)).all()
        if not old:
            continue
        db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id,
                                               DocumentChunk.embedding_model == target.model_name))
        embed_chunks(db, target, version, source, [tuple(r) for r in old], None, job.created_by)
        db.commit()
        ctx.progress(5 + int(80 * (i + 1) / total), f"Re-indexed {i + 1} of {total} sources")

    # switch
    db.execute(update(EmbeddingConfiguration).values(is_active=False))
    target.is_active, target.pending_activation = True, False
    db.execute(delete(DocumentChunk).where(DocumentChunk.embedding_model != target.model_name))
    db.commit()
    ctx.progress(90, "Re-embedding past RFP answers")
    _reembed_other(db, target)
    db.commit()
    if job.created_by:
        notify(db, job.created_by, "reindex", "Re-index completed",
               f"The Knowledge Hub now uses {target.model_name}.", "/admin/ai")
    return {"sources": len(rows)}


def _reembed_other(db: Session, cfg: EmbeddingConfiguration) -> None:
    from app.models.knowledge import SubmittedRequirementResponse

    pairs = db.scalars(select(SubmittedRequirementResponse)).all()
    for i in range(0, len(pairs), 64):
        batch = pairs[i:i + 64]
        for p, v in zip(batch, embeddings.embed(cfg, [p.requirement for p in batch])):
            p.embedding, p.embedding_model = v, cfg.model_name


def _reindex_failed(db: Session, job: Job, status: str) -> None:
    target = db.get(EmbeddingConfiguration, job.payload.get("config_id"))
    if target:
        target.pending_activation = False
        db.execute(delete(DocumentChunk).where(DocumentChunk.embedding_model == target.model_name,
                                               DocumentChunk.embedding_model != (embeddings.active_config(db).model_name
                                                                                 if embeddings.active_config(db) else "")))
    notify_permission(db, "admin.ai_config", "reindex", f"Re-index {status.lower()}",
                      "Search continues to use the previous embedding model.", "/admin/ai")


ON_END["knowledge.reindex"] = _reindex_failed


def section_stats(db: Session) -> dict[int, dict]:
    rows = db.execute(select(KnowledgeSource.section_id, KnowledgeSource.status, func.count())
                      .where(KnowledgeSource.kind != "page")  # a docs site counts once, not per page
                      .group_by(KnowledgeSource.section_id, KnowledgeSource.status)).all()
    out: dict[int, dict] = {}
    for sid, status, n in rows:
        out.setdefault(sid, {})[status] = n
    return out


from app.modules.knowledge import site_sync  # noqa: E402,F401  (registers knowledge.site_sync for the worker)

__all__ = ["ingest", "reindex", "fetch_url", "domain_allowed", "section_stats", "KnowledgeSection"]
