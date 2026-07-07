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


def sync_policy_from_doc(policy: Policy, doc: PolicyDocumentInfo, db: Session) -> None:
    """Write pipeline/scoring results from a PolicyDocumentInfo back to the row."""
    policy.has_results = doc.has_results
    policy.pipeline_errors = doc.errors
    policy.pipeline_status = (
        "succeeded" if doc.has_results else ("failed" if doc.errors else "pending")
    )
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

    db.commit()
