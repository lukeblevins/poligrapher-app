"""Mapping between DB rows and domain entities.

Keeps the DB ``Policy`` row and the ``PolicyDocumentInfo`` domain object in sync
so routers and background tasks share one conversion path.
"""

from datetime import date

from sqlalchemy.orm import Session

from poligrapher_app.api.models import AnalysisResult, Policy
from poligrapher_app.domain.policy_analysis import (
    DocumentCaptureSource,
    PolicyDocumentInfo,
)
from poligrapher_app.services.pipeline import infer_graph_kind


def policy_doc_from_db(policy: Policy) -> PolicyDocumentInfo:
    """Reconstruct a PolicyDocumentInfo from a DB row."""
    return PolicyDocumentInfo(
        path=policy.url,
        output_dir=policy.output_dir or "",
        source=DocumentCaptureSource(policy.source),
        capture_date=policy.capture_date or date.today(),
        has_results=policy.has_results,
        errors=policy.pipeline_errors or [],
    )


def sync_policy_from_doc(
    policy: Policy, doc: PolicyDocumentInfo, db: Session, *, commit: bool = True
) -> None:
    """Write pipeline/scoring results from a PolicyDocumentInfo back to the row."""
    # Pipeline status reflects whether graph artifacts exist on disk, independent
    # of scoring: a successful generate makes the policy "succeeded", and scoring
    # never gates this. (Previously both were derived from a single overloaded
    # `has_results` flag, so a generated-but-unscored policy stayed "pending".)
    policy.pipeline_errors = doc.errors
    if doc.has_graph():
        policy.pipeline_status = "succeeded"
    elif doc.errors:
        policy.pipeline_status = "failed"
    else:
        policy.pipeline_status = "pending"
    policy.graph_kind = infer_graph_kind(doc).value

    if doc.latest_privacy_result and doc.latest_privacy_result.get("success"):
        policy.privacy_score = doc.latest_privacy_result.get("total_score")
        db.add(
            AnalysisResult(
                policy_id=policy.id,
                analysis_type="privacy",
                score=policy.privacy_score,
                details=doc.latest_privacy_result,
            )
        )

    if doc.latest_gdpr_result and doc.latest_gdpr_result.get("success"):
        policy.gdpr_score = doc.latest_gdpr_result.get("total_score")
        db.add(
            AnalysisResult(
                policy_id=policy.id,
                analysis_type="gdpr",
                score=policy.gdpr_score,
                details=doc.latest_gdpr_result,
            )
        )

    # `has_results` means the policy has produced scoring results.
    policy.has_results = policy.privacy_score is not None or policy.gdpr_score is not None

    if commit:
        db.commit()
