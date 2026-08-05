"""Read-only, content-aware audits for unresolved cohort policy sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import os
import urllib.parse
import uuid

from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider, TaskIssue
from poligrapher_app.services.acquisition import PolicySourceResolver


SOURCE_FAILURE_CODES = frozenset(
    {
        "crawl.navigation_failed",
        "source.not_policy",
        "source.inaccessible",
        "source.unsupported_language",
        "pdf.invalid_source",
    }
)


@dataclass(frozen=True)
class SourceAuditTarget:
    provider_id: uuid.UUID
    provider_name: str
    domain: str | None
    source_url: str | None
    root_code: str


def _matches_provider_domain(url: str, domain: str | None) -> bool:
    expected = (domain or "").casefold().strip(". ")
    host = (urllib.parse.urlparse(url).hostname or "").casefold().strip(".")
    return bool(expected and (host == expected or host.endswith(f".{expected}")))


def source_audit_targets(
    db: Session,
    provider_ids: list[uuid.UUID],
) -> list[SourceAuditTarget]:
    """Select unresolved providers whose latest root issue is source-related."""

    if not provider_ids:
        return []
    analyzed_ids = {
        provider_id
        for provider_id, graph_data in db.query(Policy.provider_id, Policy.graph_data)
        .filter(Policy.provider_id.in_(provider_ids))
        .all()
        if isinstance(graph_data, dict) and graph_data.get("elements")
    }
    latest_code: dict[str, str] = {}
    issues = (
        db.query(TaskIssue)
        .filter(
            TaskIssue.provider_id.in_([str(provider_id) for provider_id in provider_ids]),
            TaskIssue.severity == "error",
            TaskIssue.code != "execution.subprocess_failed",
        )
        .order_by(TaskIssue.occurred_at.desc())
        .all()
    )
    for issue in issues:
        if issue.provider_id:
            latest_code.setdefault(issue.provider_id, issue.code)

    providers = (
        db.query(Provider)
        .filter(Provider.id.in_(provider_ids))
        .order_by(Provider.name)
        .all()
    )
    return [
        SourceAuditTarget(
            provider_id=provider.id,
            provider_name=provider.name,
            domain=provider.domain,
            source_url=provider.source_url,
            root_code=latest_code[str(provider.id)],
        )
        for provider in providers
        if provider.id not in analyzed_ids
        and latest_code.get(str(provider.id)) in SOURCE_FAILURE_CODES
    ]


def audit_source_target(target: SourceAuditTarget) -> dict:
    """Validate the current source and, if needed, one official replacement."""

    result = {
        **asdict(target),
        "provider_id": str(target.provider_id),
        "status": "unresolved",
        "current_valid": False,
        "current_resolved_url": None,
        "replacement_url": None,
        "replacement_strategy": None,
        "replacement_confidence": None,
        "replacement_notes": None,
    }
    resolver = PolicySourceResolver(allow_headless=False)
    try:
        if target.source_url:
            current = resolver.resolve(
                target.provider_name,
                target.domain,
                target.source_url,
            )
            if current is not None:
                result.update(
                    status="current_valid",
                    current_valid=True,
                    current_resolved_url=current.url,
                )
                return result

        candidate = resolver.resolve_candidate(
            target.provider_name,
            target.domain,
            exclude_urls={target.source_url} if target.source_url else None,
            require_validation=True,
        )
        if candidate is None:
            return result
        status = (
            "replacement_found"
            if _matches_provider_domain(candidate.url, target.domain)
            else "review_required"
        )
        result.update(
            status=status,
            replacement_url=candidate.url,
            replacement_strategy=candidate.strategy,
            replacement_confidence=candidate.confidence,
            replacement_notes=candidate.notes,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result.update(status="audit_error", error=str(exc))
        return result


def audit_source_targets(
    targets: list[SourceAuditTarget],
    *,
    on_result=None,
    should_cancel=None,
) -> dict[str, int]:
    """Audit targets concurrently without mutating provider source records."""

    counts = {
        "checked": 0,
        "current_valid": 0,
        "replacement_found": 0,
        "review_required": 0,
        "unresolved": 0,
        "audit_error": 0,
    }
    configured = int(os.getenv("COHORT_AUDIT_MAX_WORKERS", "4"))
    max_workers = max(1, min(configured, 8))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(audit_source_target, target): target for target in targets}
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                for pending in futures:
                    pending.cancel()
                break
            result = future.result()
            counts["checked"] += 1
            counts[result["status"]] += 1
            if on_result:
                on_result(result)
    return counts
