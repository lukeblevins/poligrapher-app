"""Search the Open Terms Archive service catalog for privacy-policy sources.

The public contrib declarations repository is used as a lightweight catalog.
We cache its Git tree, then fetch only the handful of declarations matching a
user query.  Failure is deliberately soft: manual company creation remains
available when GitHub or Open Terms Archive is unavailable.
"""

from __future__ import annotations

import difflib
import os
import threading
import time
import urllib.parse
from pathlib import PurePosixPath

import httpx

TREE_URL = (
    "https://api.github.com/repos/OpenTermsArchive/"
    "contrib-declarations/git/trees/main?recursive=1"
)
RAW_URL = "https://raw.githubusercontent.com/OpenTermsArchive/contrib-declarations/main/{path}"
BLOB_URL = "https://github.com/OpenTermsArchive/contrib-declarations/blob/main/{path}"
CACHE_SECONDS = 6 * 60 * 60

_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_paths: list[str] = []


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "privacy-policy-analyzer/1.0",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _declaration_paths() -> list[str]:
    global _cached_at, _cached_paths
    now = time.monotonic()
    with _cache_lock:
        if _cached_paths and now - _cached_at < CACHE_SECONDS:
            return _cached_paths
        response = httpx.get(TREE_URL, headers=_headers(), timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        paths = [
            item["path"]
            for item in response.json().get("tree", [])
            if item.get("type") == "blob"
            and item.get("path", "").startswith("declarations/")
            and item.get("path", "").endswith(".json")
            and not item.get("path", "").endswith(".history.json")
        ]
        _cached_paths = paths
        _cached_at = now
        return paths


def _display_name(path: str) -> str:
    return urllib.parse.unquote(PurePosixPath(path).stem).replace("_", " ")


def _score(name: str, query: str) -> float:
    name_key = name.casefold()
    query_key = query.casefold()
    if name_key == query_key:
        return 3.0
    if name_key.startswith(query_key):
        return 2.0
    if query_key in name_key:
        return 1.5
    return difflib.SequenceMatcher(None, query_key, name_key).ratio()


def _domain(url: str) -> str | None:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return None
    return host.removeprefix("www.").lower()


def search_open_terms(query: str, limit: int = 8) -> tuple[list[dict], bool]:
    """Return matching OTA services that declare a directly fetchable privacy policy."""
    query = query.strip()
    if len(query) < 2:
        return [], True
    try:
        paths = _declaration_paths()
    except (httpx.HTTPError, ValueError):
        return [], False

    ranked = sorted(
        ((_score(_display_name(path), query), path) for path in paths),
        reverse=True,
    )
    # Keep autocomplete trustworthy: allow close misspellings, but do not show
    # merely similar, unrelated services as though they matched the company.
    candidates = [path for score, path in ranked if score >= 0.72][: max(limit * 2, 10)]
    results: list[dict] = []
    for path in candidates:
        try:
            raw = RAW_URL.format(path=urllib.parse.quote(path, safe="/"))
            response = httpx.get(raw, timeout=8.0, follow_redirects=True)
            response.raise_for_status()
            declaration = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        policy = (declaration.get("terms") or {}).get("Privacy Policy") or {}
        source_url = policy.get("fetch")
        if not isinstance(source_url, str):
            continue
        name = declaration.get("name") or _display_name(path)
        results.append(
            {
                "id": path,
                "name": name,
                "domain": _domain(source_url),
                "source_url": source_url,
                "source": "open_terms_archive",
                "attribution_url": BLOB_URL.format(path=urllib.parse.quote(path, safe="/")),
                "requires_javascript": bool(policy.get("executeClientScripts")),
            }
        )
        if len(results) >= limit:
            break
    return results, True
