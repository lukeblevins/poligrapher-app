"""Provider analysis runs: streamlined website↔PDF comparison + one-off uploads.

A *comparison run* fetches a provider's website source once and produces two
graphs — the website-HTML method and a PDF-generated-from-that-page method —
grouped by ``run_group`` so they can be compared. A one-off *upload run* analyses
a user-provided PDF and is never scheduled; it is only re-analysed when the file
changes. Both flow through the TaskRegistry so they appear in the Status Center.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import uuid
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

def file_hash(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _score(policy, db, doc=None) -> None:
    from poligrapher_app.api.mapping import policy_doc_from_db, sync_policy_from_doc
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    doc = doc or policy_doc_from_db(policy)
    score_privacy(doc)
    score_gdpr(doc)
    sync_policy_from_doc(policy, doc, db, commit=False)


def _website_text_hash(policy, db, doc=None) -> str | None:
    from poligrapher_app.api.mapping import policy_doc_from_db
    from poligrapher_app.services.acquisition import content_hash

    try:
        return content_hash((doc or policy_doc_from_db(policy)).get_document_text())
    except Exception:  # noqa: BLE001
        return None


def _mark_failed(policies, db, message: str) -> None:
    """Terminate a run's policies as failed so the UI stops polling 'pending'.

    Reassigns pipeline_errors (rather than mutating in place) so SQLAlchemy
    tracks the change on the plain JSON column.
    """
    for p in policies:
        if not p.graph_data:
            p.pipeline_status = "failed"
        p.pipeline_errors = list(p.pipeline_errors or []) + [message]
    db.commit()


def run_comparison(
    provider_id, *, scheduled: bool, registry=None, task_id=None, link_task: bool = True
) -> str:
    """Fetch the provider's website source once and build both method graphs.

    Returns a short status string ('ok', 'unchanged', 'needs_source', 'cancelled').
    """
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy, Provider
    from poligrapher_app.services.acquisition import PolicySourceResolver
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_comparison
    from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
    from poligrapher_app.services.persistence import persist_workspace

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    db = SessionLocal()
    try:
        provider = db.get(Provider, provider_id)
        if not provider:
            return "needs_source"

        url = provider.source_url
        if not url:
            # Fall back to discovery so a run can proceed without a set source.
            cand = PolicySourceResolver().resolve_candidate(provider.name, provider.domain)
            url = cand.url if cand else None
            if url and not provider.source_url:
                provider.source_url = url
                db.commit()
        if not url:
            return "needs_source"

        # Change detection: skip scheduled runs when the policy text is unchanged.
        if scheduled:
            resolved = PolicySourceResolver().resolve(provider.name, provider.domain, url)
            if resolved is None:
                return "needs_source"
            last = (
                db.query(Policy)
                .filter_by(provider_id=provider.id, method="website")
                .filter(Policy.content_hash.isnot(None))
                .order_by(Policy.created_at.desc())
                .first()
            )
            if last and last.content_hash == resolved.content_hash:
                logger.info("Provider %s policy unchanged; skipping run", provider.name)
                return "unchanged"

        day = date.today()
        grp = uuid.uuid4()
        website = Policy(provider_id=provider.id, url=url, source="webpage", method="website",
                         run_group=grp, scheduled=scheduled, capture_date=day)
        pdf = Policy(provider_id=provider.id, url=url, source="pdf", method="pdf_from_page",
                     run_group=grp, scheduled=scheduled, capture_date=day)
        db.add_all([website, pdf])
        db.commit()
        db.refresh(website)
        db.refresh(pdf)
        if registry and task_id and link_task:
            registry.update(task_id, run_id=str(grp))

        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-", dir=temp_root) as workspace:
            web_dir = Path(workspace) / "website"
            pdf_dir = Path(workspace) / "pdf"
            try:
                generate_comparison(url, str(web_dir), str(pdf_dir), should_cancel)
                web_doc = PolicyDocumentInfo(url, str(web_dir), DocumentCaptureSource.WEBPAGE,
                                             day, False)
                pdf_doc = PolicyDocumentInfo(str(web_dir / "output.pdf"), str(pdf_dir),
                                             DocumentCaptureSource.PDF, day, False)
                _score(website, db, web_doc)
                _score(pdf, db, pdf_doc)
                persist_workspace(website, web_doc, Path(workspace) / "website.zip")
                persist_workspace(pdf, pdf_doc, Path(workspace) / "pdf.zip")
                website.content_hash = _website_text_hash(website, db, web_doc)
                db.commit()
                return "ok"
            except PipelineCancelled:
                db.rollback()
                _mark_failed([website, pdf], db, "Run cancelled")
                return "cancelled"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _mark_failed([website, pdf], db, f"Comparison failed: {exc}")
                raise
    finally:
        db.close()


def run_upload(policy_id, *, registry=None, task_id=None) -> str:
    """Analyse a one-off uploaded PDF (never scheduled)."""
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph
    from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
    from poligrapher_app.services.persistence import persist_workspace
    from poligrapher_app.services.storage import get_storage

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    db = SessionLocal()
    try:
        policy = db.get(Policy, policy_id)
        if not policy:
            return "gone"
        if not policy.source_blob_key:
            _mark_failed([policy], db, "Uploaded source is missing from object storage")
            return "gone"
        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-", dir=temp_root) as workspace:
            source = Path(workspace) / (policy.source_filename or "source.pdf")
            output = Path(workspace) / "output"
            get_storage().download_file(policy.source_blob_key, source)
            doc = PolicyDocumentInfo(str(source), str(output), DocumentCaptureSource.PDF,
                                     policy.capture_date or date.today(), policy.has_results,
                                     policy.pipeline_errors)
            try:
                generate_graph(doc, should_cancel=should_cancel)
                _score(policy, db, doc)
                persist_workspace(policy, doc, Path(workspace) / "artifacts.zip")
                policy.content_hash = file_hash(str(source))
                db.commit()
                return "ok"
            except PipelineCancelled:
                db.rollback()
                _mark_failed([policy], db, "Run cancelled")
                return "cancelled"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _mark_failed([policy], db, f"Upload analysis failed: {exc}")
                raise
    finally:
        db.close()
