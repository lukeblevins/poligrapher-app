"""Search reusable company catalogs for privacy-policy sources.

The packaged verified-source snapshot provides deterministic coverage for the
S&P 500, while Open Terms Archive adds consumer services and other companies.
Both sources share one normalizer and ranker so punctuation, legal suffixes,
tickers, domains, and policy-host names behave consistently. External failure
is deliberately soft because the packaged catalog and manual creation remain
available when Open Terms Archive is unavailable.
"""

from __future__ import annotations

import difflib
import functools
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import re
import threading
import time
import tarfile
import unicodedata
import urllib.parse
from pathlib import PurePosixPath

import httpx

from poligrapher_app.services.source_catalog import load_source_catalog

TREE_URL = (
    "https://api.github.com/repos/OpenTermsArchive/"
    "contrib-declarations/git/trees/main?recursive=1"
)
RAW_URL = "https://raw.githubusercontent.com/OpenTermsArchive/contrib-declarations/main/{path}"
BLOB_URL = "https://github.com/OpenTermsArchive/contrib-declarations/blob/main/{path}"
ARCHIVE_URL = "https://codeload.github.com/OpenTermsArchive/contrib-declarations/tar.gz/{ref}"
CACHE_SECONDS = 6 * 60 * 60
MIN_FUZZY_SCORE = 0.78
VERIFIED_CATALOG_URL = (
    "https://github.com/lukeblevins/poligrapher-app/blob/main/"
    "poligrapher_app/data/sp500_sources.json"
)

_LEGAL_SUFFIXES = {
    "company", "co", "corp", "corporation", "inc", "incorporated", "limited", "ltd", "llc",
    "plc", "holdings", "holding", "group", "class", "the",
}
_HOST_NOISE = {
    "com", "org", "net", "io", "co", "us", "uk", "www", "legal", "privacy", "policies",
    "policy", "corporate", "help", "support",
}

_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_paths: list[str] = []
_cached_tree_sha: str | None = None


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "privacy-policy-analyzer/1.0",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def open_terms_snapshot() -> tuple[list[str], str | None]:
    """Return the current declaration paths and immutable Git tree identity."""

    global _cached_at, _cached_paths, _cached_tree_sha
    now = time.monotonic()
    with _cache_lock:
        if _cached_paths and now - _cached_at < CACHE_SECONDS:
            return list(_cached_paths), _cached_tree_sha
        response = httpx.get(TREE_URL, headers=_headers(), timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        paths = [
            item["path"]
            for item in payload.get("tree", [])
            if item.get("type") == "blob"
            and item.get("path", "").startswith("declarations/")
            and item.get("path", "").endswith(".json")
            and not item.get("path", "").endswith(".history.json")
        ]
        _cached_paths = paths
        _cached_tree_sha = payload.get("sha")
        _cached_at = now
        return list(paths), _cached_tree_sha


def _declaration_paths() -> list[str]:
    paths, _tree_sha = open_terms_snapshot()
    return paths


def _display_name(path: str) -> str:
    return urllib.parse.unquote(PurePosixPath(path).stem).replace("_", " ")


def _normalized_words(value: str, *, drop_legal_suffixes: bool = False) -> str:
    value = unicodedata.normalize("NFKD", value.casefold()).replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", "".join(char for char in value if not unicodedata.combining(char)))
    if drop_legal_suffixes:
        words = [word for word in words if word not in _LEGAL_SUFFIXES]
    return " ".join(words)


def _score(name: str, query: str) -> float:
    query_key = _normalized_words(query, drop_legal_suffixes=True)
    name_keys = {
        _normalized_words(name),
        _normalized_words(name, drop_legal_suffixes=True),
    }
    if not query_key:
        return 0.0
    query_compact = query_key.replace(" ", "")
    best = 0.0
    for name_key in name_keys:
        if not name_key:
            continue
        name_compact = name_key.replace(" ", "")
        if name_key == query_key:
            score = 4.0
        elif name_compact == query_compact:
            score = 3.8
        elif name_key.startswith(query_key) or name_compact.startswith(query_compact):
            score = 3.0
        elif re.search(rf"(?:^| ){re.escape(query_key)}(?: |$)", name_key):
            score = 2.4
        else:
            score = difflib.SequenceMatcher(None, query_compact, name_compact).ratio()
        best = max(best, score)
    return best


def _domain(url: str) -> str | None:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return None
    return host.removeprefix("www.").lower()


def _host_aliases(url_or_domain: str | None) -> list[str]:
    if not url_or_domain:
        return []
    host = _domain(url_or_domain if "://" in url_or_domain else f"https://{url_or_domain}")
    if not host:
        return []
    labels = [label for label in host.split(".") if label not in _HOST_NOISE]
    return [host, *labels]


def _result_score(result: dict, query: str) -> float:
    score = _score(result["name"], query)
    query_key = _normalized_words(query).replace(" ", "")
    if any(_normalized_words(ticker).replace(" ", "") == query_key for ticker in result.get("tickers") or []):
        score = max(score, 3.9)
    host_aliases = [
        *_host_aliases(result.get("domain")),
        *_host_aliases(result.get("source_url")),
    ]
    # Host labels are useful aliases (for example Alphabet -> google.com), but
    # fuzzy domain matching creates noisy results from short ticker-like text.
    strong_host_scores = [alias_score for alias in host_aliases if (alias_score := _score(alias, query)) > 1.0]
    if strong_host_scores:
        score = max(score, max(strong_host_scores) - 0.1)
    return score


def _identity_key(name: str) -> str:
    words = _normalized_words(name, drop_legal_suffixes=True).split()
    if words and words[-1] in {"com", "net", "org"}:
        words.pop()
    return "".join(words)


def _canonical_source_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), "", "")
    )


def catalog_identity_keys(result: dict) -> tuple[str, frozenset[str], str | None]:
    """Return stable comparison keys shared by search and cohort sampling."""

    from poligrapher_app.services.acquisition import registrable_domain

    source_url = result.get("source_url")
    source = _canonical_source_key(source_url) if source_url else None
    domains = frozenset(
        domain
        for value in (result.get("domain"), source_url)
        if value and (domain := registrable_domain(value))
    )
    return _identity_key(result["name"]), domains, source


@functools.lru_cache(maxsize=1)
def _verified_catalog() -> tuple[dict, ...]:
    results = []
    for source in load_source_catalog():
        if not source.get("source_url"):
            continue
        results.append(
            {
                "id": f"verified:{source.get('cik') or source['name']}",
                "name": source["name"],
                "domain": source.get("domain") or _domain(source["source_url"]),
                "source_url": source["source_url"],
                "source": "verified_source_catalog",
                "attribution_url": VERIFIED_CATALOG_URL,
                "requires_javascript": False,
                "tickers": source.get("tickers") or [],
            }
        )
    return tuple(results)


def search_verified_catalog(query: str, limit: int = 8) -> list[dict]:
    """Search the packaged verified sources without network access."""
    query = query.strip()
    if len(query) < 2:
        return []
    ranked = sorted(
        ((_result_score(result, query), result) for result in _verified_catalog()),
        key=lambda item: (-item[0], item[1]["name"].casefold()),
    )
    return [dict(result) for score, result in ranked if score >= MIN_FUZZY_SCORE][:limit]


def verified_catalog_entries() -> list[dict]:
    """Return a copy of every packaged catalog entry for bounded experiments."""

    return [dict(result) for result in _verified_catalog()]


def _open_terms_entry(path: str, declaration: dict) -> tuple[dict | None, str | None]:
    policy = (declaration.get("terms") or {}).get("Privacy Policy") or {}
    source_url = policy.get("fetch")
    if not isinstance(source_url, str):
        return None, "no_fetchable_privacy_policy"
    name = declaration.get("name") or _display_name(path)
    return {
        "id": path,
        "name": name,
        "domain": _domain(source_url),
        "source_url": source_url,
        "source": "open_terms_archive",
        "attribution_url": BLOB_URL.format(path=urllib.parse.quote(path, safe="/")),
        "requires_javascript": bool(policy.get("executeClientScripts")),
    }, None


def fetch_open_terms_entry(path: str) -> tuple[dict | None, str | None]:
    """Materialize one OTA declaration and explain why unusable entries failed."""

    try:
        raw = RAW_URL.format(path=urllib.parse.quote(path, safe="/"))
        response = httpx.get(raw, timeout=8.0, follow_redirects=True)
        response.raise_for_status()
        declaration = response.json()
    except (httpx.HTTPError, ValueError):
        return None, "fetch_error"
    return _open_terms_entry(path, declaration)


def parse_open_terms_archive(content: bytes) -> list[dict]:
    """Read every declaration from a tar archive without extracting files."""

    loaded: list[dict] = []
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
        members = sorted(
            (
                member
                for member in archive.getmembers()
                if member.isfile()
                and "/declarations/" in member.name
                and member.name.endswith(".json")
                and not member.name.endswith(".history.json")
            ),
            key=lambda member: member.name,
        )
        for member in members:
            path = "declarations/" + member.name.split("/declarations/", 1)[1]
            stream = archive.extractfile(member)
            if stream is None:
                loaded.append({"path": path, "entry": None, "rejection": "archive_read_error"})
                continue
            try:
                declaration = json.loads(stream.read())
                entry, rejection = _open_terms_entry(path, declaration)
            except (UnicodeDecodeError, ValueError, TypeError):
                entry, rejection = None, "invalid_declaration"
            loaded.append({"path": path, "entry": entry, "rejection": rejection})
    return loaded


def download_open_terms_catalog(tree_sha: str | None) -> list[dict]:
    """Materialize the immutable OTA snapshot with one bounded download."""

    response = httpx.get(
        ARCHIVE_URL.format(ref=tree_sha or "main"),
        headers=_headers(),
        timeout=60.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return parse_open_terms_archive(response.content)


def load_open_terms_catalog(
    paths: list[str] | None = None,
    *,
    max_workers: int = 8,
) -> list[dict]:
    """Fetch declarations concurrently, preserving path order and failures."""

    selected_paths = paths if paths is not None else _declaration_paths()
    workers = max(1, min(max_workers, 8))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        loaded = executor.map(fetch_open_terms_entry, selected_paths)
        return [
            {"path": path, "entry": entry, "rejection": rejection}
            for path, (entry, rejection) in zip(selected_paths, loaded, strict=True)
        ]


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
    candidates = [path for score, path in ranked if score >= MIN_FUZZY_SCORE][: max(limit * 2, 10)]
    results: list[dict] = []
    # A query can have several plausible declarations. Materialize them with a
    # bounded worker pool so autocomplete latency does not grow linearly with
    # the number of candidates.
    for item in load_open_terms_catalog(candidates):
        entry = item["entry"]
        if entry is None:
            continue
        results.append(entry)
        if len(results) >= limit:
            break
    return results, True


def search_company_catalog(query: str, limit: int = 8) -> tuple[list[dict], bool]:
    """Merge verified and OTA matches, preferring the strongest company identity."""
    query = query.strip()
    if len(query) < 2:
        return [], True

    verified = search_verified_catalog(query, limit=max(limit * 2, 10))
    open_terms, _open_terms_available = search_open_terms(query, limit=max(limit * 2, 10))
    ranked = sorted(
        (
            (_result_score(result, query), result)
            for result in [*verified, *open_terms]
        ),
        key=lambda item: (-item[0], item[1]["name"].casefold()),
    )

    results: list[dict] = []
    seen_sources: set[str] = set()
    seen_companies: set[str] = set()
    for score, result in ranked:
        if score < MIN_FUZZY_SCORE:
            continue
        company_key, _domain_keys, source_key = catalog_identity_keys(result)
        if source_key in seen_sources or company_key in seen_companies:
            continue
        seen_sources.add(source_key)
        seen_companies.add(company_key)
        cleaned = dict(result)
        cleaned.pop("tickers", None)
        results.append(cleaned)
        if len(results) >= limit:
            break
    # The packaged catalog is always available, even if the OTA extension is not.
    return results, True
