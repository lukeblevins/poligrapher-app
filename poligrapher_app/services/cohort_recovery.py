"""State-safe primitives for repeatable cohort source recovery."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Callable
import uuid

from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.domain.policy_state import has_graph_elements
from poligrapher_app.services import cohort_audit
from poligrapher_app.services.cohort_audit import AuditStatus, SourceAuditResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSourceSnapshot:
    source_url: str | None
    source_status: str
    source_checked_at: datetime | None
    source_http_status: int | None
    source_final_url: str | None

    @classmethod
    def capture(cls, provider: Provider) -> "ProviderSourceSnapshot":
        return cls(
            source_url=provider.source_url,
            source_status=provider.source_status,
            source_checked_at=provider.source_checked_at,
            source_http_status=provider.source_http_status,
            source_final_url=provider.source_final_url,
        )

    def restore(self, provider: Provider) -> None:
        provider.source_url = self.source_url
        provider.source_status = self.source_status
        provider.source_checked_at = self.source_checked_at
        provider.source_http_status = self.source_http_status
        provider.source_final_url = self.source_final_url


def recovery_url(result: SourceAuditResult) -> str | None:
    """Return only a resolver-validated URL that is safe to auto-try."""

    return result.auto_attempt_url


def _merge_audit_result(
    fast_result: SourceAuditResult,
    deep_result: SourceAuditResult,
) -> SourceAuditResult:
    """Keep a completed fast decision when optional enrichment times out."""

    if (
        deep_result.status is AuditStatus.AUDIT_ERROR
        and fast_result.status is not AuditStatus.AUDIT_ERROR
    ):
        return fast_result
    return deep_result


def stage_source(db: Session, provider: Provider, url: str) -> ProviderSourceSnapshot:
    snapshot = ProviderSourceSnapshot.capture(provider)
    provider.source_url = url
    provider.source_status = "unchecked"
    provider.source_checked_at = None
    provider.source_http_status = None
    provider.source_final_url = None
    db.commit()
    return snapshot


def restore_source(db: Session, provider: Provider, snapshot: ProviderSourceSnapshot) -> None:
    snapshot.restore(provider)
    db.commit()


def accept_source(db: Session, provider: Provider, url: str) -> None:
    provider.source_url = url
    provider.source_status = "available"
    provider.source_checked_at = datetime.now(timezone.utc)
    provider.source_final_url = url
    db.commit()


def has_completed_graph(db: Session, provider_id: uuid.UUID) -> bool:
    return any(
        has_graph_elements(graph_data)
        for graph_data, in db.query(Policy.graph_data)
        .filter(Policy.provider_id == provider_id)
        .all()
    )


def _terminal_issue(result: SourceAuditResult) -> dict | None:
    """Translate a safe non-action into the same issue model used by the UI."""

    if result.status is AuditStatus.REVIEW_REQUIRED:
        return {
            "code": "recovery.review_required",
            "stage": "source_resolution",
            "severity": "warning",
            "retryability": "manual",
            "summary": "A possible policy source needs review",
            "technical_detail": json.dumps(result.as_record(), sort_keys=True),
            "actions": [
                {"action": "replace_source", "label": "Review and confirm the candidate source"},
                {"action": "review_content", "label": "Check that it is the general privacy policy"},
            ],
        }
    if result.status is AuditStatus.UNRESOLVED:
        return {
            "code": "recovery.unresolved",
            "stage": "source_resolution",
            "severity": "warning",
            "retryability": "manual",
            "summary": "No safe policy source was found automatically",
            "technical_detail": json.dumps(result.as_record(), sort_keys=True),
            "actions": [
                {"action": "replace_source", "label": "Set a verified policy source"},
                {"action": "upload_pdf", "label": "Upload an official policy PDF"},
            ],
        }
    if result.status is AuditStatus.AUDIT_ERROR:
        return {
            "code": "recovery.audit_error",
            "stage": "source_resolution",
            "severity": "error",
            "retryability": "transient",
            "summary": "The policy-source audit could not complete",
            "technical_detail": result.error or "Source audit failed",
            "actions": [{"action": "retry", "label": "Retry recovery"}],
        }
    return None


class CohortRecoveryRunner:
    """Coordinate repeatable recovery while keeping task dispatch generic."""

    def __init__(
        self,
        *,
        task_id: str,
        payload: dict,
        registry,
        session_factory,
        analyze_provider: Callable[[str, uuid.UUID, object], str],
    ) -> None:
        self.task_id = task_id
        self.payload = payload
        self.registry = registry
        self.session_factory = session_factory
        self.analyze_provider = analyze_provider

    def _set_phase(self, label: str) -> None:
        self.registry.update(self.task_id, label=label)
        self.registry.append_output(self.task_id, f"RECOVERY PHASE: {label}\n")

    def _record_result(self, result: SourceAuditResult, **recovery: str) -> None:
        record = result.as_record()
        record.update({key: value for key, value in recovery.items() if value})
        self.registry.append_output(
            self.task_id,
            json.dumps(record, sort_keys=True) + "\n",
        )

    def _record_terminal_issue(self, result: SourceAuditResult) -> None:
        issue = _terminal_issue(result)
        if issue:
            self.registry.record_issue(
                self.task_id,
                issue,
                provider_id=result.provider_id,
            )

    def _advance_analysis_phase(self, completed: int, total: int) -> None:
        self.registry.update(
            self.task_id,
            label=f"Analyzing recovery candidates ({completed}/{total})",
        )

    def run(self) -> None:
        all_provider_ids = [uuid.UUID(value) for value in self.payload.get("provider_ids", [])]
        task = self.registry.get(self.task_id) or {}
        start_index = min(int(task.get("completed") or 0), len(all_provider_ids))
        provider_ids = all_provider_ids[start_index:]
        with self.session_factory() as db:
            targets = cohort_audit.source_audit_targets(db, provider_ids)
        targets_by_id = {target.provider_id: target for target in targets}

        self._set_phase(f"Auditing sources (0/{len(targets)})")
        fast_results: dict[uuid.UUID, SourceAuditResult] = {}

        def record_fast(result: SourceAuditResult) -> None:
            fast_results[result.provider_id] = result
            self.registry.update(
                self.task_id,
                label=f"Auditing sources ({len(fast_results)}/{len(targets)})",
            )

        cohort_audit.audit_source_targets(
            targets,
            on_result=record_fast,
            should_cancel=lambda: self.registry.is_cancelled(self.task_id),
            deep=False,
        )
        final_results = dict(fast_results)
        if self.payload.get("deep", True) and not self.registry.is_cancelled(self.task_id):
            deep_targets = [
                targets_by_id[provider_id]
                for provider_id, result in fast_results.items()
                if result.status in {AuditStatus.UNRESOLVED, AuditStatus.AUDIT_ERROR}
            ]
            self._set_phase(f"Deep-auditing sources (0/{len(deep_targets)})")
            deep_completed = 0

            def record_deep(result: SourceAuditResult) -> None:
                nonlocal deep_completed
                final_results[result.provider_id] = _merge_audit_result(
                    fast_results[result.provider_id],
                    result,
                )
                deep_completed += 1
                self.registry.update(
                    self.task_id,
                    label=f"Deep-auditing sources ({deep_completed}/{len(deep_targets)})",
                )

            cohort_audit.audit_source_targets(
                deep_targets,
                on_result=record_deep,
                should_cancel=lambda: self.registry.is_cancelled(self.task_id),
                deep=True,
            )
        if self.registry.is_cancelled(self.task_id):
            self.registry.set_cancelled(self.task_id)
            return

        counts = Counter({
            "targeted": len(provider_ids),
            "attempted": 0,
            "recovered": 0,
            "rolled_back": 0,
            "analysis_failed": 0,
            "review_required": 0,
            "unresolved": 0,
            "audit_error": 0,
            "already_resolved": 0,
        })
        self._set_phase(f"Analyzing recovery candidates (0/{len(provider_ids)})")
        for index, provider_id in enumerate(provider_ids, start=1):
            if self.registry.is_cancelled(self.task_id):
                self.registry.set_cancelled(self.task_id)
                return
            result = final_results.get(provider_id)
            if result is None:
                counts["already_resolved"] += 1
                self.registry.append_output(self.task_id, json.dumps({
                    "provider_id": str(provider_id), "status": "already_resolved",
                }, sort_keys=True) + "\n")
                self.registry.incr(self.task_id, "completed")
                self._advance_analysis_phase(index, len(provider_ids))
                continue
            url = recovery_url(result)
            if not url:
                counts[result.status.value] += 1
                self._record_terminal_issue(result)
                if result.status is AuditStatus.AUDIT_ERROR:
                    self.registry.incr(self.task_id, "failed")
                self._record_result(result)
                self.registry.incr(self.task_id, "completed")
                self._advance_analysis_phase(index, len(provider_ids))
                continue

            counts["attempted"] += 1
            replacement = result.status is AuditStatus.REPLACEMENT_FOUND
            snapshot = None
            recovery_status = ""
            analysis_detail = ""
            recovery_error = ""
            try:
                with self.session_factory() as db:
                    provider = db.get(Provider, provider_id)
                    if provider is None:
                        raise RuntimeError(f"Provider {provider_id} no longer exists")
                    snapshot = stage_source(db, provider, url)
                analysis_result = self.analyze_provider(self.task_id, provider_id, self.registry)
                if analysis_result == "cancelled":
                    with self.session_factory() as db:
                        provider = db.get(Provider, provider_id)
                        if provider is not None and snapshot is not None:
                            restore_source(db, provider, snapshot)
                    self.registry.set_cancelled(self.task_id)
                    return
                with self.session_factory() as db:
                    provider = db.get(Provider, provider_id)
                    if provider is None:
                        raise RuntimeError(f"Provider {provider_id} no longer exists")
                    recovered = (
                        analysis_result in {"ok", "unchanged"}
                        and has_completed_graph(db, provider_id)
                    )
                    if recovered:
                        accept_source(db, provider, url)
                    elif snapshot is not None:
                        restore_source(db, provider, snapshot)
                if recovered:
                    counts["recovered"] += 1
                    recovery_status = "recovered"
                else:
                    counts["rolled_back"] += int(replacement)
                    counts["analysis_failed"] += int(not replacement)
                    self.registry.incr(self.task_id, "failed")
                    recovery_status = "rolled_back" if replacement else "analysis_failed"
                    analysis_detail = analysis_result
            except Exception as exc:  # noqa: BLE001
                logger.exception("Cohort recovery failed for provider %s", provider_id)
                if snapshot is not None:
                    with self.session_factory() as db:
                        provider = db.get(Provider, provider_id)
                        if provider is not None:
                            restore_source(db, provider, snapshot)
                    counts["rolled_back"] += int(replacement)
                    counts["analysis_failed"] += int(not replacement)
                self.registry.incr(self.task_id, "failed")
                recovery_status = "rolled_back" if replacement else "analysis_failed"
                recovery_error = str(exc)
            self._record_result(
                result,
                recovery_status=recovery_status,
                analysis_result=analysis_detail,
                error=recovery_error,
            )
            self.registry.incr(self.task_id, "completed")
            self._advance_analysis_phase(index, len(provider_ids))

        self.registry.append_output(
            self.task_id,
            "RECOVERY SUMMARY: " + json.dumps(dict(counts), sort_keys=True) + "\n",
        )
        settled = self.registry.get(self.task_id) or {}
        if int(settled.get("failed") or 0):
            self.registry.update(
                self.task_id,
                error="Recovery completed with unresolved execution errors; successful repairs were retained.",
            )
        self.registry.set_done(
            self.task_id,
            has_issues=bool(counts["review_required"] or counts["unresolved"]),
        )
