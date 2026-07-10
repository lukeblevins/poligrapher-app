"""CSV import service.

Shared by the ``POST /api/providers/import`` endpoint and the ``migrate_csv``
seed command so both use one code path for turning a policy-list CSV into
Provider/Policy rows.
"""

import io
import logging

import pandas as pd
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.utils import best_website_url, parse_date, parse_pipeline_errors


def read_policy_csv(content: bytes) -> pd.DataFrame:
    """Parse policy-list CSV bytes into a stripped-header DataFrame."""
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def import_policies(df: pd.DataFrame, db: Session) -> dict:
    """Upsert providers + policies from a DataFrame. Returns import counts."""
    created = skipped = errors = 0

    for provider_name, group in df.groupby("Provider"):
        try:
            provider = db.query(Provider).filter_by(name=provider_name).first()
            if provider is None:
                industry = group["Industry"].iloc[0] or None
                provider = Provider(name=provider_name, industry=industry)
                db.add(provider)
                db.flush()

            for _, row in group.iterrows():
                url = row.get("Policy URL", "").strip()
                source = row.get("Source", "webpage").strip().lower()
                capture_date = parse_date(row.get("Date", ""))

                exists = db.query(Policy).filter_by(
                    provider_id=provider.id, url=url, source=source, capture_date=capture_date
                ).first()
                if exists:
                    skipped += 1
                    continue

                privacy_raw = row.get("Score", "").strip()
                gdpr_raw = row.get("GDPR Score", "").strip()

                db.add(
                    Policy(
                        provider_id=provider.id,
                        url=url,
                        source=source,
                        capture_date=capture_date,
                        has_results=row.get("Status", "False").strip().lower() == "true",
                        pipeline_status=row.get("Pipeline Status", "pending").strip().lower() or "pending",
                        pipeline_errors=parse_pipeline_errors(row.get("Pipeline Errors", "")),
                        privacy_score=float(privacy_raw) if privacy_raw else None,
                        gdpr_score=float(gdpr_raw) if gdpr_raw else None,
                        graph_kind=row.get("Graph Kind", "none").strip().lower() or "none",
                    )
                )
                created += 1

            # Prefill the provider's website source from its (successful) policies.
            db.flush()
            if not provider.source_url:
                provider.source_url = best_website_url(provider.policies)
        except Exception:
            logger.exception("Failed to import rows for provider %r", provider_name)
            errors += 1
            db.rollback()
            continue

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
