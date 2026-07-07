"""Seed the database from ``policy_list.csv``.

Usage:
    python -m poligrapher_app.migrate_csv [path/to/policy_list.csv]

Defaults to the bundled ``poligrapher_app/policy_list.csv``. Safe to re-run —
existing providers/policies are skipped, not duplicated.
"""

import sys
from pathlib import Path

import poligrapher_app.api.models  # noqa: F401 — register tables for create_all
from poligrapher_app.api.database import Base, SessionLocal, engine
from poligrapher_app.services.importer import import_policies, read_policy_csv

DEFAULT_CSV = Path(__file__).parent / "policy_list.csv"


def main(csv_path: str | Path = DEFAULT_CSV) -> None:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    Base.metadata.create_all(bind=engine)
    df = read_policy_csv(csv_path.read_bytes())

    db = SessionLocal()
    try:
        summary = import_policies(df, db)
    finally:
        db.close()

    print(
        f"Seed complete — {summary['created']} created, "
        f"{summary['skipped']} skipped, {summary['errors']} errors."
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV)
