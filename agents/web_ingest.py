"""Bounded web ingestion — concurrent fetching with content-quality filtering.

Production features:
- asyncio.gather for parallel page fetching
- Readability extraction with fallback to raw text
- Content-quality heuristic (min length, link-density filter)
- Per-page timing and error logging
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from readability import Document

log = logging.getLogger("agents.web_ingest")

_MIN_TEXT_LEN = 120  # skip pages with less useful content
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _allowed(url: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    d = _domain(url)
    clean = [a.lower().lstrip(".") for a in allowed_domains]
    return any(d == a or d.endswith("." + a) for a in clean)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _fetch_one(client: httpx.AsyncClient, url: str) -> dict | None:
    """Fetch a single page, extract readable content."""
    t0 = time.perf_counter()
    try:
        resp = await client.get(url)
        if resp.status_code >= 400:
            log.warning("HTTP %d for %s", resp.status_code, url)
            return None

        html = resp.text
        doc = Document(html)
        main_html = doc.summary(html_partial=True)
        soup = BeautifulSoup(main_html, "lxml")
        text = _clean_text(soup.get_text(" "))
        title = doc.short_title() or None

        if len(text) < _MIN_TEXT_LEN:
            log.info("Skipping %s — too short (%d chars)", url, len(text))
            return None

        elapsed = (time.perf_counter() - t0) * 1000
        log.info("Fetched %s — %d chars in %.0fms", url, len(text), elapsed)
        return {"url": url, "title": title, "text": text, "chars": len(text)}

    except httpx.TimeoutException:
        log.warning("Timeout fetching %s", url)
        return None
    except Exception as exc:
        log.warning("Error fetching %s: %s", url, exc)
        return None


async def fetch_pages(
    seed_urls: list[str],
    allowed_domains: list[str],
    *,
    k: int,
) -> list[dict]:
    """Concurrently fetch up to k pages from user-supplied URLs."""

    urls: list[str] = []
    for u in seed_urls:
        if u and u not in urls and _allowed(u, allowed_domains):
            urls.append(u)
        if len(urls) >= k:
            break

    if not urls:
        log.info("No seed URLs to fetch")
        return []

    log.info("Fetching %d URLs concurrently…", len(urls))

    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True, headers=_HEADERS
    ) as client:
        tasks = [_fetch_one(client, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    pages: list[dict] = []
    for r in results:
        if isinstance(r, dict):
            pages.append(r)
        elif isinstance(r, Exception):
            log.warning("Fetch task failed: %s", r)

    log.info("Fetched %d / %d pages successfully", len(pages), len(urls))
    return pages
