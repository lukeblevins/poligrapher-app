"""CSV import service.

Shared by the ``POST /api/providers/import`` endpoint and the ``migrate_csv``
seed command so both use one code path for turning a policy-list CSV into
Provider/Policy rows.
"""

import io
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.utils import parse_date, parse_pipeline_errors

# Mirrors the layout produced by add_policy / the pipeline:
# output/<Provider_Slug>/<capture_date>_<source>/
OUTPUT_BASE = Path(__file__).parent.parent.parent / "output"


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

                # Derive the artifact directory from the naming convention so
                # seeded policies can locate graphs already on disk.
                output_dir = None
                if capture_date:
                    slug = str(provider_name).replace(" ", "_")
                    output_dir = str(OUTPUT_BASE / slug / f"{capture_date.isoformat()}_{source}")

                db.add(
                    Policy(
                        provider_id=provider.id,
                        url=url,
                        source=source,
                        capture_date=capture_date,
                        output_dir=output_dir,
                        has_results=row.get("Status", "False").strip().lower() == "true",
                        pipeline_status=row.get("Pipeline Status", "pending").strip().lower() or "pending",
                        pipeline_errors=parse_pipeline_errors(row.get("Pipeline Errors", "")),
                        privacy_score=float(privacy_raw) if privacy_raw else None,
                        gdpr_score=float(gdpr_raw) if gdpr_raw else None,
                        graph_kind=row.get("Graph Kind", "none").strip().lower() or "none",
                    )
                )
                created += 1
        except Exception:
            errors += 1
            db.rollback()
            continue

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
