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
import uuid
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_BASE = Path(__file__).parent.parent.parent / "output"


def file_hash(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _score(policy, db) -> None:
    from poligrapher_app.api.mapping import policy_doc_from_db, sync_policy_from_doc
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    doc = policy_doc_from_db(policy)
    score_privacy(doc)
    score_gdpr(doc)
    sync_policy_from_doc(policy, doc, db)


def _website_text_hash(policy, db) -> str | None:
    from poligrapher_app.api.mapping import policy_doc_from_db
    from poligrapher_app.services.acquisition import content_hash

    try:
        return content_hash(policy_doc_from_db(policy).get_document_text())
    except Exception:  # noqa: BLE001
        return None


def _mark_failed(policies, db, message: str) -> None:
    """Terminate a run's policies as failed so the UI stops polling 'pending'.

    Reassigns pipeline_errors (rather than mutating in place) so SQLAlchemy
    tracks the change on the plain JSON column.
    """
    for p in policies:
        p.pipeline_status = "failed"
        p.pipeline_errors = list(p.pipeline_errors or []) + [message]
    db.commit()


def run_comparison(provider_id, *, scheduled: bool, registry=None, task_id=None) -> str:
    """Fetch the provider's website source once and build both method graphs.

    Returns a short status string ('ok', 'unchanged', 'needs_source', 'cancelled').
    """
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy, Provider
    from poligrapher_app.api.utils import provider_slug
    from poligrapher_app.services.acquisition import PolicySourceResolver
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_comparison

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
        slug = provider_slug(provider.name)
        tag = grp.hex[:8]
        web_dir = OUTPUT_BASE / slug / f"{day.isoformat()}_website_{tag}"
        pdf_dir = OUTPUT_BASE / slug / f"{day.isoformat()}_pdf_{tag}"

        website = Policy(provider_id=provider.id, url=url, source="webpage", method="website",
                         run_group=grp, scheduled=scheduled, capture_date=day, output_dir=str(web_dir))
        pdf = Policy(provider_id=provider.id, url=url, source="pdf", method="pdf_from_page",
                     run_group=grp, scheduled=scheduled, capture_date=day, output_dir=str(pdf_dir))
        db.add_all([website, pdf])
        db.commit()
        db.refresh(website)
        db.refresh(pdf)

        try:
            generate_comparison(url, str(web_dir), str(pdf_dir), should_cancel)
        except PipelineCancelled:
            _mark_failed([website, pdf], db, "Run cancelled")
            return "cancelled"
        except Exception as exc:  # noqa: BLE001
            _mark_failed([website, pdf], db, f"Comparison failed: {exc}")
            raise

        _score(website, db)
        _score(pdf, db)
        website.content_hash = _website_text_hash(website, db)
        db.commit()
        return "ok"
    finally:
        db.close()


def run_upload(policy_id, *, registry=None, task_id=None) -> str:
    """Analyse a one-off uploaded PDF (never scheduled)."""
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import policy_doc_from_db
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    db = SessionLocal()
    try:
        policy = db.get(Policy, policy_id)
        if not policy:
            return "gone"
        doc = policy_doc_from_db(policy)
        try:
            generate_graph(doc, should_cancel=should_cancel)
        except PipelineCancelled:
            _mark_failed([policy], db, "Run cancelled")
            return "cancelled"
        except Exception as exc:  # noqa: BLE001
            _mark_failed([policy], db, f"Upload analysis failed: {exc}")
            raise
        # _score() re-reads the generated doc, scores it, and syncs+commits — no
        # second sync of the pre-generate `doc` (that clobbered the scored fields).
        _score(policy, db)
        policy.content_hash = file_hash(policy.url)
        db.commit()
        return "ok"
    finally:
        db.close()
