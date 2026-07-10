"""Import legacy output directories into durable database/blob persistence.

Dry-run is the default. Use ``--apply`` only after reviewing the summary.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.api.models import Policy
from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
from poligrapher_app.services.persistence import canonical_results, create_artifact_archive
from poligrapher_app.services.storage import artifact_key, get_storage, source_key


def migrate(*, apply: bool = False) -> dict[str, int]:
    summary = {"eligible": 0, "migrated": 0, "skipped": 0, "errors": 0}
    storage = get_storage()
    db = SessionLocal()
    try:
        for policy in db.query(Policy).order_by(Policy.created_at):
            if policy.graph_data:
                summary["skipped"] += 1
                continue
            root = Path(policy.output_dir or "")
            if not policy.output_dir or not root.is_dir():
                summary["skipped"] += 1
                continue
            try:
                source = DocumentCaptureSource.PDF if policy.source == "pdf" else DocumentCaptureSource.WEBPAGE
                doc = PolicyDocumentInfo(policy.url, str(root), source,
                                         policy.capture_date or policy.created_at.date(),
                                         policy.has_results, policy.pipeline_errors)
                graph_data, stats = canonical_results(doc)
                if not graph_data["elements"]:
                    summary["skipped"] += 1
                    continue
                summary["eligible"] += 1
                if not apply:
                    continue
                with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
                    create_artifact_archive(root, archive.name)
                    archive_blob = artifact_key(policy.id)
                    storage.upload_file(archive_blob, archive.name, content_type="application/zip")
                if policy.method == "pdf_upload" and Path(policy.url).is_file():
                    filename = Path(policy.url).name
                    source_blob = source_key(policy.id, filename)
                    storage.upload_file(source_blob, policy.url, content_type="application/pdf")
                    policy.source_blob_key = source_blob
                    policy.source_filename = filename
                    policy.url = filename
                policy.graph_data = graph_data
                policy.graph_stats = stats
                policy.artifact_blob_key = archive_blob
                policy.persistence_status = "persisted"
                db.commit()
                summary["migrated"] += 1
            except Exception:  # keep the importer resumable policy-by-policy
                db.rollback()
                summary["errors"] += 1
        return summary
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    result = migrate(apply=args.apply)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: " + ", ".join(f"{key}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
