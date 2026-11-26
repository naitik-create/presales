"""Documentation sites in the Knowledge Hub: finding a site's pages (sitemap first, then links), and telling which
pages are new, changed or gone. Pure functions (no database or network) so they are easy to test.

A site such as https://docs.motadata.com/observeops-docs/ is one KnowledgeSource (kind "site"); each page under it is
its own KnowledgeSource (kind "page") whose URL starts with the site URL, so answers cite the exact page.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urldefrag, urljoin, urlparse, urlunparse

DEFAULT_LIMIT = 3000
MAX_LIMIT = 10000
DEFAULT_DELAY_MS = 300
# Pages that carry no product content (Docusaurus tag, search and placeholder pages, assets).
DEFAULT_EXCLUDE = ["/tags/", "/search", "/markdown-page", "/blog/", "/page/", "/assets/", "/img/"]
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js", ".json", ".xml", ".zip", ".mp4",
            ".woff", ".woff2", ".ttf", ".pdf")
SETTING_PREFIX = "knowledge_site:"
ZIP_MANIFEST = "manifest.json"


def base_url(url: str) -> str:
    """The site URL every page must start with: scheme and host lower-case, no query or fragment, ending in '/'."""
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Enter a full http or https address")
    path = p.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))


def clean_url(url: str) -> str:
    url, _ = urldefrag(url.strip())
    p = urlparse(url)
    path = re.sub(r"/{2,}", "/", p.path or "/")
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", p.query, ""))


def rehost(url: str, base: str) -> str:
    """Some doc sites list their pages under another host in the sitemap (docs.motadata.com lists
    www.motadata.com/observeops-docs/..., which does not resolve). Move such URLs onto the site's own host."""
    b, u = urlparse(base), urlparse(url)
    if u.netloc.lower() != b.netloc and unquote(u.path).startswith(unquote(b.path)):
        return urlunparse((b.scheme, b.netloc, u.path, "", u.query, ""))
    return url


def in_scope(url: str, base: str, exclude: list[str] | None = None) -> bool:
    u, b = urlparse(url), urlparse(base)
    if u.scheme not in ("http", "https") or u.netloc.lower() != b.netloc:
        return False
    path = unquote(u.path)
    if not (path + "/").startswith(unquote(b.path)) or path.lower().endswith(SKIP_EXT):
        return False
    return not any(x and x.lower() in path.lower() for x in (exclude or []))


def parse_sitemap(xml: str | bytes) -> tuple[list[str], list[str]]:
    """(page URLs, child sitemap URLs) from a sitemap or sitemap index. Namespaces are ignored."""
    try:
        root = ET.fromstring(xml if isinstance(xml, bytes) else xml.encode())
    except ET.ParseError:
        return [], []
    tag = root.tag.split("}")[-1]
    locs = [(e.text or "").strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and (e.text or "").strip()]
    return ([], locs) if tag == "sitemapindex" else (locs, [])


def page_key(url: str, base: str) -> str:
    """One spelling per page: cleaned, without a trailing slash (except the site's own start page)."""
    u = clean_url(url)
    return u if u == base else u.rstrip("/")


def scope_urls(urls: list[str], base: str, exclude: list[str], limit: int) -> tuple[list[str], bool]:
    """Re-host, clean, keep the ones under the site, de-duplicate in order. Returns (urls, truncated)."""
    seen: dict[str, None] = {}
    for u in urls:
        u = clean_url(rehost(u, base))
        if in_scope(u, base, exclude):
            seen.setdefault(page_key(u, base), None)
    out = list(seen)
    return out[:limit], len(out) > limit


def links(html: str, page_url: str, base: str, exclude: list[str]) -> list[str]:
    """Links on a page that stay inside the site (used when a site has no sitemap)."""
    out: dict[str, None] = {}
    for href in re.findall(r"""href\s*=\s*["']([^"'#][^"']*)["']""", html, flags=re.I):
        u = clean_url(urljoin(page_url, href.strip()))
        if in_scope(u, base, exclude):
            out.setdefault(page_key(u, base), None)
    return list(out)


def page_title(html: str, fallback: str) -> str:
    for pat in (r"<h1[^>]*>(.*?)</h1>", r"<title[^>]*>(.*?)</title>"):
        m = re.search(pat, html, flags=re.I | re.S)
        if m:
            t = re.sub(r"<[^>]+>", " ", m.group(1)).replace("\u200b", "")
            t = " ".join(re.sub(r"&(amp|nbsp|#39|quot);", lambda x: {"amp": "&", "nbsp": " ", "#39": "'", "quot": '"'}[x.group(1)], t).split())
            t = re.sub(r"\s*\|\s*[^|]*$", "", t) if pat.startswith("<title") else t  # "Page | Site name"
            if t:
                return t[:300]
    path = unquote(urlparse(fallback).path).rstrip("/").split("/")[-1] or fallback
    return path.replace("-", " ").replace("_", " ")[:300]


# Page furniture on documentation sites (Docusaurus and similar): table of contents, breadcrumbs, previous/next links,
# "edit this page", heading anchor links.
CHROME_CLASSES = ("table-of-contents", "theme-doc-toc", "pagination-nav", "breadcrumbs", "theme-edit-this-page",
                  "theme-last-updated", "hash-link", "theme-doc-footer", "theme-doc-sidebar")


def strip_chrome(html: str) -> str:
    """Remove navigation furniture so only the page's own content is indexed."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(class_=lambda c: c and any(x in str(c) for x in CHROME_CLASSES)):
        el.decompose()
    for el in soup.find_all(["aside"]):
        el.decompose()
    return str(soup).replace("\u200b", "")


def text_hash(segments: list[tuple[str, str]]) -> str:
    """Hash of a page's extracted text (section, text). Compared on re-sync: page HTML changes on every site build
    (script names), the text only when the page really changes."""
    h = hashlib.sha256()
    for section, text in segments:
        h.update(f"{section}\x1f{' '.join(text.split())}\n".encode())
    return h.hexdigest()


def plan_changes(existing: dict[str, str], fetched: dict[str, str], complete: bool) -> dict[str, list[str]]:
    """existing / fetched: url -> text hash ("" for a page that could not be read). Pages missing from a complete
    page list are removed; a truncated list (page limit reached) removes nothing."""
    out: dict[str, list[str]] = {"new": [], "changed": [], "unchanged": [], "removed": []}
    for url, h in fetched.items():
        if not h:
            continue
        key = "new" if url not in existing else "unchanged" if existing[url] == h else "changed"
        out[key].append(url)
    if complete:
        out["removed"] = [u for u in existing if u not in fetched]
    return out


def read_manifest(data: bytes) -> dict:
    m = json.loads(data.decode("utf-8"))
    if not isinstance(m, dict) or not isinstance(m.get("pages"), list):
        raise ValueError("manifest.json has no page list")
    return m
