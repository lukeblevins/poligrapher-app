"""Read-only, content-aware audits for unresolved cohort policy sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import multiprocessing
import os
import urllib.parse
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider, TaskIssue, TaskRecord
from poligrapher_app.domain.policy_state import has_graph_elements
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


class AuditStatus(StrEnum):
    """Every terminal decision produced by a source audit."""

    CURRENT_VALID = "current_valid"
    RETRY_CURRENT = "retry_current"
    REPLACEMENT_FOUND = "replacement_found"
    REVIEW_REQUIRED = "review_required"
    UNRESOLVED = "unresolved"
    AUDIT_ERROR = "audit_error"


@dataclass(frozen=True)
class SourceAuditTarget:
    provider_id: uuid.UUID
    provider_name: str
    domain: str | None
    source_url: str | None
    root_code: str
    root_retryability: str = "manual"
    source_revalidated: bool = False


@dataclass
class SourceAuditResult:
    """Typed contract shared by audit, recovery, reporting, and tests."""

    target: SourceAuditTarget
    status: AuditStatus = AuditStatus.UNRESOLVED
    current_valid: bool = False
    current_resolved_url: str | None = None
    replacement_url: str | None = None
    replacement_strategy: str | None = None
    replacement_confidence: float | None = None
    replacement_notes: str | None = None
    error: str | None = None

    @property
    def provider_id(self) -> uuid.UUID:
        return self.target.provider_id

    @property
    def auto_attempt_url(self) -> str | None:
        if self.status in {AuditStatus.CURRENT_VALID, AuditStatus.RETRY_CURRENT}:
            return self.current_resolved_url or self.target.source_url
        if self.status is AuditStatus.REPLACEMENT_FOUND:
            return self.replacement_url
        return None

    def as_record(self) -> dict:
        record = {
            **asdict(self.target),
            "provider_id": str(self.target.provider_id),
            "status": self.status.value,
            "current_valid": self.current_valid,
            "current_resolved_url": self.current_resolved_url,
            "replacement_url": self.replacement_url,
            "replacement_strategy": self.replacement_strategy,
            "replacement_confidence": self.replacement_confidence,
            "replacement_notes": self.replacement_notes,
        }
        if self.error:
            record["error"] = self.error
        return record


def _matches_provider_domain(url: str, domain: str | None) -> bool:
    expected = (domain or "").casefold().strip(". ").removeprefix("www.")
    host = (urllib.parse.urlparse(url).hostname or "").casefold().strip(".")
    # A registrable-domain match alone is not enough for unattended recovery:
    # product, workforce, investor, and historical microsites commonly live on
    # first-party subdomains. Keep those candidates visible for review, while
    # allowing only the company's canonical apex/www hosts to auto-run.
    return bool(expected and host in {expected, f"www.{expected}"})


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


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_after(left: datetime | None, right: datetime | None) -> bool:
    normalized_left = _utc(left)
    normalized_right = _utc(right)
    return bool(
        normalized_left is not None
        and normalized_right is not None
        and normalized_left > normalized_right
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
        if has_graph_elements(graph_data)
    }
    latest_issue: dict[str, tuple[str, str, datetime]] = {}
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
            latest_issue.setdefault(
                issue.provider_id,
                (issue.code, issue.retryability, issue.occurred_at),
            )

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
            root_code=latest_issue[str(provider.id)][0],
            root_retryability=latest_issue[str(provider.id)][1],
            source_revalidated=bool(
                provider.source_status == "available"
                and _is_after(
                    provider.source_checked_at,
                    latest_issue[str(provider.id)][2],
                )
            ),
        )
        for provider in providers
        if provider.id not in analyzed_ids
        and latest_issue.get(str(provider.id), (None, None, None))[0] in AUDITABLE_FAILURE_CODES
    ]


def audit_source_target(target: SourceAuditTarget, *, deep: bool = False) -> SourceAuditResult:
    """Validate the current source and, if needed, one official replacement."""

    result = SourceAuditResult(target=target)
    # A source verified after the recorded failure is a new recovery input,
    # including for graph.empty. Analyze it once before searching for another
    # representation. Standardized transient failures likewise authorize a
    # direct retry of the configured source.
    if target.source_url and (
        target.source_revalidated or target.root_retryability == "transient"
    ):
        result.status = AuditStatus.RETRY_CURRENT
        result.current_resolved_url = target.source_url
        return result
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
                result.status = AuditStatus.CURRENT_VALID
                result.current_valid = True
                result.current_resolved_url = target.source_url
                return result

        candidate = None
        if target.source_url and target.root_code == "graph.empty":
            linked_resolver = getattr(resolver, "resolve_linked_candidate", None)
            if linked_resolver:
                candidate = linked_resolver(
                    target.provider_name,
                    target.domain,
                    target.source_url,
                    timeout=15.0 if deep else 12.0,
                    max_validation_candidates=3 if deep else 2,
                )
        if candidate is None:
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
        if (
            candidate.strategy != "search"
            and not getattr(candidate, "validated", False)
        ):
            candidate_html = fetch_validated_policy_html(candidate.url)
            if not candidate_html:
                return result
        result.status = (
            AuditStatus.REPLACEMENT_FOUND
            if (
                _matches_provider_domain(candidate.url, target.domain)
                and candidate.confidence >= AUTO_CONFIDENCE
            )
            else AuditStatus.REVIEW_REQUIRED
        )
        result.replacement_url = candidate.url
        result.replacement_strategy = candidate.strategy
        result.replacement_confidence = candidate.confidence
        result.replacement_notes = candidate.notes
        return result
    except Exception as exc:  # noqa: BLE001
        result.status = AuditStatus.AUDIT_ERROR
        result.error = str(exc)
        return result


def _audit_source_target_child(target: SourceAuditTarget, deep: bool, connection) -> None:
    """Run one network-heavy audit in a process the parent can terminate."""

    try:
        connection.send(audit_source_target(target, deep=deep))
    except BaseException as exc:  # noqa: BLE001
        connection.send(SourceAuditResult(
            target=target,
            status=AuditStatus.AUDIT_ERROR,
            error=f"Audit subprocess failed: {type(exc).__name__}: {exc}",
        ))
    finally:
        connection.close()


def _run_audit_source_target(
    target: SourceAuditTarget,
    *,
    deep: bool,
    timeout_seconds: float | None = None,
    context=None,
) -> SourceAuditResult:
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
            return SourceAuditResult(
                target=target,
                status=AuditStatus.AUDIT_ERROR,
                error=f"Source audit exceeded {timeout_seconds:g} seconds",
            )
        if receiver.poll():
            return receiver.recv()
        return SourceAuditResult(
            target=target,
            status=AuditStatus.AUDIT_ERROR,
            error=f"Audit subprocess exited with code {process.exitcode} without a result",
        )
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

    counts = {"checked": 0, **{status.value: 0 for status in AuditStatus}}
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
            counts[result.status.value] += 1
            if on_result:
                on_result(result)
    return counts
