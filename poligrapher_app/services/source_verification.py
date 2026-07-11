"""Lightweight availability checks for configured provider policy sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from poligrapher_app.api.models import Provider
from poligrapher_app.services.acquisition import BROWSER_HEADERS


@dataclass(frozen=True)
class SourceCheck:
    provider_id: object
    status: str
    http_status: int | None
    final_url: str | None


def _check(client: httpx.Client, provider: Provider) -> SourceCheck:
    if not provider.source_url:
        return SourceCheck(provider.id, "missing", None, None)
    try:
        with client.stream("GET", provider.source_url) as response:
            status_code = response.status_code
            final_url = str(response.url)
            # Read only enough to prove the response has a body; closing the
            # stream avoids downloading large policy PDFs during verification.
            next(response.iter_bytes(8192), b"")
    except (httpx.HTTPError, ValueError):
        return SourceCheck(provider.id, "error", None, None)

    # Some CDNs route browser-fingerprint headers to a stale edge while a
    # plain standards-compliant request succeeds. Before declaring a 404/410,
    # retry without the shared Chrome client to avoid a false broken result.
    if status_code in (404, 410):
        try:
            with httpx.stream(
                "GET",
                provider.source_url,
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
    with httpx.Client(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0) as client:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check, client, provider): provider for provider in providers}
            for future in as_completed(futures):
                if should_cancel and should_cancel():
                    for pending in futures:
                        pending.cancel()
                    break
                check = future.result()
                provider = db.get(Provider, check.provider_id)
                if provider is None:
                    continue
                provider.source_status = check.status
                provider.source_checked_at = checked_at
                provider.source_http_status = check.http_status
                provider.source_final_url = check.final_url
                counts["checked"] += 1
                key = "errors" if check.status == "error" else check.status
                counts[key] += 1
                if on_result:
                    on_result(check)
    db.commit()
    return counts
