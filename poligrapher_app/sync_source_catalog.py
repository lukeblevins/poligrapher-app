"""Apply the checked-in verified source catalog to the configured database."""

from __future__ import annotations

from dataclasses import asdict

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.services.source_catalog import apply_source_catalog, load_source_catalog


def main() -> None:
    with SessionLocal() as db:
        summary = apply_source_catalog(db, load_source_catalog())
    print(asdict(summary))


if __name__ == "__main__":
    main()
