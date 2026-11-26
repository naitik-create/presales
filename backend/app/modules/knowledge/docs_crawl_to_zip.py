#!/usr/bin/env python3
"""Save a documentation site to a ZIP for the Presales platform's Knowledge Hub ("Import ZIP" on a docs site).

Use it when the platform's server cannot reach the site. Needs only Python 3.8+ (no extra packages):

    python3 docs_crawl_to_zip.py https://docs.motadata.com/observeops-docs/
    python3 docs_crawl_to_zip.py https://docs.motadata.com/serviceops-docs/ --limit 3000 --delay 0.3

It reads the site's sitemap (or follows links when there is none), downloads each page under the address politely
(one at a time, with a pause) and writes <site>.zip with the pages and a manifest.json. Nothing else is collected.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from urllib.parse import unquote, urldefrag, urljoin, urlparse, urlunparse

UA = "MotadataPresalesBot/1.0 (+internal; docs export)"
EXCLUDE = ["/tags/", "/search", "/markdown-page", "/blog/", "/page/", "/assets/", "/img/"]
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js", ".json", ".xml", ".zip", ".mp4",
            ".woff", ".woff2", ".ttf", ".pdf")


def base_url(url):
    p = urlparse(url.strip())
    path = p.path if p.path.endswith("/") else (p.path or "") + "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))


def clean(url):
    url, _ = urldefrag(url.strip())
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), re.sub(r"/{2,}", "/", p.path or "/"), "", p.query, ""))


def key(url, base):
    u = clean(url)
    return u if u == base else u.rstrip("/")


def rehost(url, base):
    b, u = urlparse(base), urlparse(url)
    if u.netloc.lower() != b.netloc and unquote(u.path).startswith(unquote(b.path)):
        return urlunparse((b.scheme, b.netloc, u.path, "", u.query, ""))
    return url


def in_scope(url, base):
    u, b = urlparse(url), urlparse(base)
    path = unquote(u.path)
    return (u.scheme in ("http", "https") and u.netloc.lower() == b.netloc and (path + "/").startswith(unquote(b.path))
            and not path.lower().endswith(SKIP_EXT) and not any(x in path.lower() for x in EXCLUDE))


class Getter:
    def __init__(self, delay):
        self.delay, self.last = delay, 0.0

    def get(self, url):
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.headers.get("content-type", ""), r.read(), r.geturl()


def sitemap_pages(g, base):
    todo, seen, found = [base + "sitemap.xml"], set(), []
    while todo and len(seen) < 50:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            _s, _c, body, _u = g.get(sm)
            root = ET.fromstring(body)
        except Exception:
            continue
        locs = [(e.text or "").strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and (e.text or "").strip()]
        if root.tag.split("}")[-1] == "sitemapindex":
            todo += [rehost(x, base) for x in locs]
        else:
            found += locs
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="site address, e.g. https://docs.motadata.com/observeops-docs/")
    ap.add_argument("--limit", type=int, default=3000, help="most pages to save (default 3000)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests (default 0.3)")
    ap.add_argument("--out", help="ZIP file name (default: from the site address)")
    a = ap.parse_args()
    base = base_url(a.url)
    g = Getter(a.delay)
    print(f"Reading the sitemap of {base} ...")
    urls = []
    for u in sitemap_pages(g, base):
        u = key(rehost(u, base), base)
        if in_scope(u, base) and u not in urls:
            urls.append(u)
    how = "sitemap"
    if not urls:
        print("No sitemap; following links instead ...")
        how, queue = "links", [base]
        while queue and len(urls) < a.limit:
            u = queue.pop(0)
            if u in urls:
                continue
            urls.append(u)
            try:
                _s, ctype, body, final = g.get(u)
            except Exception:
                continue
            if "html" in ctype:
                for href in re.findall(r"""href\s*=\s*["']([^"'#][^"']*)["']""", body.decode("utf-8", "replace"), re.I):
                    x = key(urljoin(final, href), base)
                    if in_scope(x, base) and x not in urls and x not in queue:
                        queue.append(x)
    truncated = len(urls) > a.limit
    urls = urls[:a.limit]
    name = a.out or (re.sub(r"[^A-Za-z0-9]+", "-", urlparse(base).netloc + urlparse(base).path).strip("-") + ".zip")
    pages, failed = [], 0
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for i, u in enumerate(urls, start=1):
            try:
                status, ctype, body, _final = g.get(u)
                if status != 200 or "html" not in ctype:
                    raise ValueError(f"HTTP {status} {ctype}")
                f = f"pages/{i:05d}.html"
                z.writestr(f, body)
                pages.append({"url": u, "file": f})
            except (urllib.error.URLError, ValueError, OSError) as e:
                failed += 1
                print(f"  failed {u}: {e}", file=sys.stderr)
            if i % 25 == 0 or i == len(urls):
                print(f"  {i} of {len(urls)} pages")
        z.writestr("manifest.json", json.dumps({
            "base": base, "how": how, "made_at": datetime.now(timezone.utc).isoformat(), "truncated": truncated,
            "pages": pages}, indent=1))
    print(f"Saved {len(pages)} pages ({failed} failed) to {name}. Upload it in Knowledge Hub > the site > Import ZIP.")


if __name__ == "__main__":
    main()
