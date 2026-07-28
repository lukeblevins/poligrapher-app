"""Lightweight availability checks for configured provider policy sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

import httpx
from sqlalchemy.orm import Session

from poligrapher_app.api.models import Provider
from poligrapher_app.services.acquisition import (
    BROWSER_HEADERS,
    PolicySourceResolver,
    reader_snapshot_url,
    wayback_snapshot_url,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceCheck:
    provider_id: object
    status: str
    http_status: int | None
    final_url: str | None


def _check(client: httpx.Client, provider: Provider) -> SourceCheck:
    source_url = provider.source_url
    discovered = not source_url
    if not source_url:
        resolved = PolicySourceResolver(allow_headless=False).resolve_candidate(
            provider.name, provider.domain
        )
        if not resolved:
            return SourceCheck(provider.id, "missing", None, None)
        source_url = resolved.url
    try:
        with client.stream("GET", source_url) as response:
            status_code = response.status_code
            final_url = str(response.url)
            # Read only enough to prove the response has a body; closing the
            # stream avoids downloading large policy PDFs during verification.
            next(response.iter_bytes(8192), b"")
    except (httpx.HTTPError, ValueError):
        # Retain a confidently discovered canonical URL even when this
        # lightweight worker cannot reach the corporate site. The analysis
        # pipeline has browser, proxy, archive, and PDF acquisition fallbacks.
        archived = wayback_snapshot_url(source_url, timeout=8.0, raw=False)
        if archived:
            return SourceCheck(provider.id, "available", None, archived)
        mirrored = reader_snapshot_url(source_url, provider.name, timeout=20.0)
        if mirrored:
            return SourceCheck(provider.id, "available", None, mirrored)
        return SourceCheck(provider.id, "error", None, source_url if discovered else None)

    # Some CDNs route browser-fingerprint headers to a stale edge while a
    # plain standards-compliant request succeeds. Before declaring a 404/410,
    # retry without the shared Chrome client to avoid a false broken result.
    if status_code in (404, 410):
        try:
            with httpx.stream(
                "GET",
                source_url,
                follow_redirects=True,
                timeout=15.0,
                headers={"User-Agent": "curl/8.7.1", "Accept": "*/*"},
            ) as response:
                if 200 <= response.status_code < 400:
                    status_code = response.status_code
                    final_url = str(response.url)
                    next(response.iter_bytes(8192), b"")
        except (httpx.HTTPError, ValueError):
            pass

    if 200 <= status_code < 400:
        status = "available"
    elif status_code in (401, 403, 407, 429, 451):
        status = "restricted"
    elif status_code in (404, 410):
        status = "broken"
    else:
        status = "error"
    if status != "available":
        archived = wayback_snapshot_url(source_url, timeout=8.0, raw=False)
        if archived:
            return SourceCheck(provider.id, "available", status_code, archived)
        mirrored = reader_snapshot_url(source_url, provider.name, timeout=20.0)
        if mirrored:
            return SourceCheck(provider.id, "available", status_code, mirrored)
        if status_code == 429:
            # The analysis fetcher retries throttled sources through its
            # configured proxy route, so a confirmed rate limit is recoverable.
            return SourceCheck(provider.id, "available", status_code, source_url)
    return SourceCheck(provider.id, status, status_code, final_url)


def verify_provider_sources(
    db: Session,
    providers: list[Provider] | None = None,
    *,
    max_workers: int = 8,
    on_result=None,
    should_cancel=None,
) -> dict[str, int]:
    providers = providers if providers is not None else db.query(Provider).all()
    counts = {"checked": 0, "available": 0, "restricted": 0, "broken": 0, "errors": 0, "missing": 0}
    checked_at = datetime.now(timezone.utc)
    pending_commits = 0
    with httpx.Client(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0) as client:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check, client, provider): provider for provider in providers}
            for future in as_completed(futures):
                if should_cancel and should_cancel():
                    for pending in futures:
                        pending.cancel()
                    break
                try:
                    check = future.result()
                except Exception:  # noqa: BLE001
                    provider = futures[future]
                    logger.exception("Source verification failed for %s", provider.name)
                    check = SourceCheck(provider.id, "error", None, provider.source_url)
                provider = db.get(Provider, check.provider_id)
                if provider is None:
                    continue
                if not provider.source_url and check.final_url:
                    provider.source_url = check.final_url
                provider.source_status = check.status
                provider.source_checked_at = checked_at
                provider.source_http_status = check.http_status
                provider.source_final_url = check.final_url
                counts["checked"] += 1
                key = "errors" if check.status == "error" else check.status
                counts[key] += 1
                pending_commits += 1
                if pending_commits >= 10:
                    db.commit()
                    pending_commits = 0
                if on_result:
                    on_result(check)
    db.commit()
    return counts
