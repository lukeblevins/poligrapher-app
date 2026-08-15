"""Read-only, content-aware audits for unresolved cohort policy sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import multiprocessing
import os
import urllib.parse
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider, TaskIssue, TaskRecord
from poligrapher_app.services.acquisition import (
    AUTO_CONFIDENCE,
    PolicySourceResolver,
    fetch_validated_policy_html,
)


SOURCE_FAILURE_CODES = frozenset(
    {
        "crawl.navigation_failed",
        "source.not_policy",
        "source.inaccessible",
        "source.unsupported_language",
        "pdf.invalid_source",
        "pdf.download_timeout",
    }
)
AUDITABLE_FAILURE_CODES = SOURCE_FAILURE_CODES | {"graph.empty"}


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


def _source_identity(url: str | None) -> str:
    """Normalize superficial URL differences before comparing source identity."""

    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        ("", f"{host}{port}", path, parsed.query, "")
    )


def source_audit_targets(
    db: Session,
    provider_ids: list[uuid.UUID],
) -> list[SourceAuditTarget]:
    """Select unresolved providers with source or representation failures."""

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
        .join(TaskRecord, TaskIssue.task_id == TaskRecord.id)
        .filter(
            TaskIssue.provider_id.in_([str(provider_id) for provider_id in provider_ids]),
            TaskIssue.severity == "error",
            TaskIssue.code != "execution.subprocess_failed",
            or_(TaskRecord.kind.is_(None), TaskRecord.kind != "cohort-recovery"),
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
        and latest_code.get(str(provider.id)) in AUDITABLE_FAILURE_CODES
    ]


def audit_source_target(target: SourceAuditTarget, *, deep: bool = False) -> dict:
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
        # An empty graph already proves the current source reached the pipeline.
        # Auditing it again only repeats work; look for a distinct official
        # representation that may expose the policy more cleanly instead.
        if target.source_url and target.root_code != "graph.empty":
            current_html = fetch_validated_policy_html(
                target.source_url,
                timeout=20.0 if deep else 12.0,
                attempts=1,
            )
            if current_html:
                result.update(
                    status="current_valid",
                    current_valid=True,
                    current_resolved_url=target.source_url,
                )
                return result

        candidate = resolver.resolve_candidate(
            target.provider_name,
            target.domain,
            exclude_urls={target.source_url} if target.source_url else None,
            require_validation=True,
            search_timeout=15.0 if deep else 12.0,
            max_validation_candidates=3 if deep else 2,
            allow_site_discovery=deep,
        )
        if candidate is None:
            return result
        if _source_identity(candidate.url) == _source_identity(target.source_url):
            return result
        # Search candidates were validated by the resolver. Deep discovery and
        # sitemap candidates must satisfy the same analyzer-facing contract
        # before the audit is allowed to describe them as replacements.
        if candidate.strategy != "search":
            candidate_html = fetch_validated_policy_html(candidate.url)
            if not candidate_html:
                return result
        status = (
            "replacement_found"
            if (
                _matches_provider_domain(candidate.url, target.domain)
                and candidate.confidence >= AUTO_CONFIDENCE
            )
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


def _audit_source_target_child(target: SourceAuditTarget, deep: bool, connection) -> None:
    """Run one network-heavy audit in a process the parent can terminate."""

    try:
        connection.send(audit_source_target(target, deep=deep))
    except BaseException as exc:  # noqa: BLE001
        connection.send(
            {
                **asdict(target),
                "provider_id": str(target.provider_id),
                "status": "audit_error",
                "error": f"Audit subprocess failed: {type(exc).__name__}: {exc}",
            }
        )
    finally:
        connection.close()


def _run_audit_source_target(
    target: SourceAuditTarget,
    *,
    deep: bool,
    timeout_seconds: float | None = None,
    context=None,
) -> dict:
    """Return one audit result within a true wall-clock deadline."""

    timeout_seconds = timeout_seconds or (150.0 if deep else 75.0)
    context = context or multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_audit_source_target_child,
        args=(target, deep, sender),
        daemon=True,
    )
    try:
        process.start()
        sender.close()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(5.0)
            return {
                **asdict(target),
                "provider_id": str(target.provider_id),
                "status": "audit_error",
                "error": f"Source audit exceeded {timeout_seconds:g} seconds",
            }
        if receiver.poll():
            return receiver.recv()
        return {
            **asdict(target),
            "provider_id": str(target.provider_id),
            "status": "audit_error",
            "error": f"Audit subprocess exited with code {process.exitcode} without a result",
        }
    finally:
        receiver.close()
        if not sender.closed:
            sender.close()


def audit_source_targets(
    targets: list[SourceAuditTarget],
    *,
    on_result=None,
    should_cancel=None,
    deep: bool = False,
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
    configured = int(os.getenv("COHORT_AUDIT_MAX_WORKERS", "8"))
    max_workers = max(1, min(configured, 8))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_audit_source_target, target, deep=deep): target
            for target in targets
        }
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
