"""Documentation site sync (see sites.py): fetch or import a site's pages and index only what changed.

A site's settings and last sync report are kept in system_settings under "knowledge_site:<id>" (no migration).
Pages of an approved site are approved with it; a page that changes on the site stays approved (it is the
official documentation) and is listed in the sync report. Pages no longer on the site are disabled.
"""
from __future__ import annotations

import io
import time
import zipfile

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai import embeddings
from app.core.jobs import ON_END, JobContext, handler
from app.core.notify import notify_permission
from app.core.settings_store import get_setting, set_setting
from app.core.storage import read_file
from app.db import utcnow
from app.models.core import Job, StoredFile
from app.models.knowledge import DocumentChunk, DocumentVersion, KnowledgeSource
from app.modules.knowledge import sites
from app.modules.knowledge.service import USER_AGENT, domain_allowed, embed_chunks
from app.parsing.chunk import chunk_segments
from app.parsing.extract import html_to_segments

MAX_FAILED_IN_REPORT = 200


def config(db: Session, site_id: int) -> dict:
    c = get_setting(db, f"{sites.SETTING_PREFIX}{site_id}") or {}
    return {"page_limit": sites.DEFAULT_LIMIT, "delay_ms": sites.DEFAULT_DELAY_MS, "exclude": list(sites.DEFAULT_EXCLUDE),
            "report": None, **c}


def save_config(db: Session, site_id: int, values: dict) -> dict:
    c = {**config(db, site_id), **values}
    set_setting(db, f"{sites.SETTING_PREFIX}{site_id}", c)
    return c


def pages_query(site: KnowledgeSource):
    return select(KnowledgeSource).where(KnowledgeSource.kind == "page", KnowledgeSource.url.startswith(site.url))


def page_counts(db: Session, site: KnowledgeSource) -> dict:
    rows = db.execute(select(KnowledgeSource.status, KnowledgeSource.ingest_status, func.count())
                      .where(KnowledgeSource.kind == "page", KnowledgeSource.url.startswith(site.url))
                      .group_by(KnowledgeSource.status, KnowledgeSource.ingest_status)).all()
    out = {"total": 0, "approved": 0, "pending": 0, "disabled": 0, "failed": 0}
    for status, ingest, n in rows:
        out["total"] += n
        if ingest == "Failed":
            out["failed"] += n
        key = {"Approved": "approved", "Pending": "pending", "Disabled": "disabled", "Rejected": "disabled"}.get(status)
        if key:
            out[key] += n
    return out


def cascade_status(db: Session, site: KnowledgeSource, status: str, user_id: int | None) -> int:
    """The site was approved, rejected, disabled or enabled: its pages follow. Pages removed from the site stay
    disabled; pages that could not be read are left as they are."""
    n = 0
    for p in db.scalars(pages_query(site)):
        if p.ingest_status != "Ready" or p.ingest_error.startswith("Not on the site"):
            continue
        p.status = status
        if status == "Approved":
            p.approved_by, p.approved_at = user_id, utcnow()
        n += 1
    return n


# ---------- getting the pages ----------
class Fetcher:
    def __init__(self, db: Session, delay_ms: int):
        self.db, self.delay, self.last = db, max(0, delay_ms) / 1000, 0.0
        self.client = httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def get(self, url: str) -> httpx.Response:
        if not domain_allowed(self.db, url):
            raise ValueError("Domain not on the allowed list (Administration > Settings)")
        for attempt in (1, 2):
            wait = self.delay - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                r = self.client.get(url)
                if r.status_code >= 500 and attempt == 1:
                    continue
                if not domain_allowed(self.db, str(r.url)):
                    raise ValueError("Redirected to a domain that is not allowed")
                return r
            except httpx.TransportError:
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")


def discover(f: Fetcher, base: str, cfg: dict, ctx: JobContext) -> tuple[list[str], bool, str]:
    """(page URLs, truncated, how) from the sitemap(s) under the site, or by following links when there are none."""
    limit, exclude = cfg["page_limit"], cfg["exclude"]
    found: list[str] = []
    todo, seen = [base + "sitemap.xml"], set()
    while todo and len(seen) < 50:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            r = f.get(sm)
        except Exception:
            continue
        if r.status_code != 200 or "<" not in r.text[:200]:
            continue
        urls, children = sites.parse_sitemap(r.content)
        found += urls
        todo += [sites.rehost(c, base) for c in children]
    if found:
        urls, truncated = sites.scope_urls(found, base, exclude, limit)
        return urls, truncated, "sitemap"
    # no sitemap: follow links from the start page, breadth first
    queue, pages = [base], {}
    while queue and len(pages) < limit:
        u = queue.pop(0)
        if u in pages:
            continue
        try:
            r = f.get(u)
        except Exception:
            pages[u] = None
            continue
        pages[u] = None
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            queue += [x for x in sites.links(r.text, str(r.url), base, exclude) if x not in pages]
        if len(pages) % 25 == 0:
            ctx.progress(3, f"Following links: {len(pages)} pages found")
            ctx.check()
    return list(pages), bool(queue), "links"


def _zip_pages(db: Session, file_id: int, base: str, cfg: dict) -> tuple[dict[str, bytes], bool]:
    """Pages from a ZIP made by the crawl script on a machine with internet access."""
    f = db.get(StoredFile, file_id)
    z = zipfile.ZipFile(io.BytesIO(read_file(f)))
    m = sites.read_manifest(z.read(sites.ZIP_MANIFEST))
    if sites.base_url(m.get("base") or base) != base:
        raise ValueError(f"This ZIP was made for {m.get('base')}, not {base}")
    out: dict[str, bytes] = {}
    for p in m["pages"]:
        url = sites.page_key(sites.rehost(p.get("url", ""), base), base)
        if sites.in_scope(url, base, cfg["exclude"]) and p.get("file") in z.namelist():
            out[url] = z.read(p["file"])
    urls, truncated = sites.scope_urls(list(out), base, cfg["exclude"], cfg["page_limit"])
    return {u: out[u] for u in urls}, truncated or bool(m.get("truncated"))


# ---------- indexing ----------
def _index_page(db: Session, site: KnowledgeSource, page: KnowledgeSource | None, url: str, html: str,
                cfg_emb, chunk_cfg: dict, user_id: int | None) -> tuple[str, KnowledgeSource | None]:
    """Returns (outcome, page): outcome is new, changed, unchanged or failed:<reason>."""
    ex = html_to_segments(sites.strip_chrome(html), url)
    segs = [s for s in ex.segments if len(s.text) > 2]
    if not segs:
        return "failed:No text on the page", page
    digest = sites.text_hash([(s.section, s.text) for s in segs])
    if page is not None:
        cur = db.scalar(select(DocumentVersion).where(DocumentVersion.source_id == page.id,
                                                     DocumentVersion.version == page.current_version))
        removed_before = page.ingest_error.startswith("Not on the site")
        page.last_fetch_attempt_at = page.last_fetch_ok_at = utcnow()
        if cur and cur.sha256 == digest and page.ingest_status == "Ready" and cur.embedding_model == cfg_emb.model_name:
            if removed_before:  # back on the site
                page.ingest_error, page.status = "", site.status if site.status == "Approved" else "Pending"
            return "unchanged", page
    title = sites.page_title(html, url)
    outcome = "changed" if page is not None else "new"
    if page is None:
        page = KnowledgeSource(section_id=site.section_id, kind="page", url=url, title=title, product=site.product,
                               product_version=site.product_version, document_type="Online documentation",
                               label=site.label, created_by=user_id,
                               status="Approved" if site.status == "Approved" else "Pending")
        if page.status == "Approved":
            page.approved_by, page.approved_at = site.approved_by, utcnow()
        db.add(page)
        db.flush()
    else:
        page.title, page.product, page.product_version, page.label = title, site.product, site.product_version, site.label
        if page.ingest_error.startswith("Not on the site"):
            page.status = "Approved" if site.status == "Approved" else "Pending"
    n = (db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.source_id == page.id)) or 0) + 1
    v = DocumentVersion(source_id=page.id, version=n, sha256=digest, page_count=1, embedding_model=cfg_emb.model_name)
    db.add(v)
    db.flush()
    chunks = chunk_segments(segs, chunk_cfg["chunk_chars"], chunk_cfg["chunk_overlap"])
    embed_chunks(db, cfg_emb, v, page, [(c.text, c.section_path or title, c.page) for c in chunks], None, user_id)
    db.execute(delete(DocumentChunk).where(DocumentChunk.source_id == page.id, DocumentChunk.version_id != v.id))
    page.current_version, page.ingest_status, page.ingest_error = n, "Ready", ""
    page.last_fetch_attempt_at = page.last_fetch_ok_at = utcnow()
    return outcome, page


@handler("knowledge.site_sync")
def site_sync(db: Session, job: Job, ctx: JobContext) -> dict:
    site = db.get(KnowledgeSource, job.payload["site_id"])
    cfg = config(db, site.id)
    emb = embeddings.active_config(db)
    if emb is None:
        raise RuntimeError("No embedding model is active")
    chunk_cfg = get_setting(db, "retrieval")
    site.ingest_status, site.last_fetch_attempt_at = "Processing", utcnow()
    db.commit()
    mode = job.payload.get("mode", "crawl")
    f = Fetcher(db, cfg["delay_ms"])
    ctx.progress(2, "Finding the pages")
    if mode == "zip":
        zipped, truncated = _zip_pages(db, job.payload["file_id"], site.url, cfg)
        urls, how = list(zipped), "ZIP import"
    else:
        zipped = {}
        urls, truncated, how = discover(f, site.url, cfg, ctx)
    if not urls:
        raise ValueError("No pages found under this address (no sitemap and no links)")
    existing = {p.url: p for p in db.scalars(pages_query(site))}
    counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0, "failed": 0}
    failed: list[dict] = []
    changed: list[str] = []
    seen: set[str] = set()
    for i, url in enumerate(urls, start=1):
        ctx.check()
        page = existing.get(url)
        try:
            if mode == "zip":
                html = zipped[url].decode("utf-8", errors="replace")
            else:
                r = f.get(url)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                if "html" not in r.headers.get("content-type", "html"):
                    raise ValueError(f"Not a web page ({r.headers.get('content-type', '')})")
                html = r.text
            outcome, page = _index_page(db, site, page, url, html, emb, chunk_cfg, job.created_by)
            seen.add(url)
        except Exception as e:  # one bad page must not stop the sync
            db.rollback()
            page = existing.get(url)  # a page created before the error was rolled back with it
            outcome = f"failed:{str(e)[:200] or e.__class__.__name__}"
            seen.add(url)  # it is still on the site
        if outcome.startswith("failed:"):
            counts["failed"] += 1
            if len(failed) < MAX_FAILED_IN_REPORT:
                failed.append({"url": url, "error": outcome[7:]})
            if page is not None:
                page.last_fetch_attempt_at = utcnow()
        else:
            counts[outcome] += 1
            if outcome == "changed" and len(changed) < MAX_FAILED_IN_REPORT:
                changed.append(url)
        db.commit()
        if i % 10 == 0 or i == len(urls):
            ctx.progress(5 + int(90 * i / len(urls)),
                         f"{i} of {len(urls)} pages: {counts['new']} new, {counts['changed']} changed, {counts['failed']} failed")
    if not truncated:
        for url, p in existing.items():
            if url not in seen and not p.ingest_error.startswith("Not on the site"):
                p.status, p.ingest_error = "Disabled", f"Not on the site any more (sync {utcnow():%d %b %Y})"
                counts["removed"] += 1
    site.ingest_status, site.ingest_error = "Ready", ""
    site.last_fetch_ok_at = utcnow()
    site.current_version = (site.current_version or 0) + 1
    report = {"at": utcnow().isoformat(), "how": how, "pages_found": len(urls), "truncated": truncated, **counts,
              "failed_pages": failed, "changed_pages": changed}
    save_config(db, site.id, {"report": report})
    db.commit()
    if site.status == "Pending":
        notify_permission(db, "knowledge.approve", "site_synced", f"Docs site ready for approval: {site.title}",
                          f"{len(urls)} pages indexed. Approve the site to use them in answers.", "/knowledge?tab=sites")
        db.commit()
    return {k: v for k, v in report.items() if k not in ("failed_pages", "changed_pages")}


def _sync_failed(db: Session, job: Job, status: str) -> None:
    site = db.get(KnowledgeSource, job.payload.get("site_id"))
    if site:
        site.ingest_status = "Failed" if not site.current_version else "Ready"
        site.ingest_error = (job.error or status).split("\n")[0][:500]
        notify_permission(db, "knowledge.approve", "ingestion_failed", f"Docs site sync {status.lower()}: {site.title}",
                          site.ingest_error, "/knowledge?tab=sites")


ON_END["knowledge.site_sync"] = _sync_failed
