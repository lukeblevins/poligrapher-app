"""Copy a migrated local database and object store into cloud persistence.

Required environment variables:
    TARGET_DATABASE_URL
    AZURE_STORAGE_CONNECTION_STRING
Optional:
    SOURCE_DATABASE_URL (default sqlite:///./poligrapher.db)
    LOCAL_STORAGE_ROOT (default ./storage)
    AZURE_STORAGE_CONTAINER (default poligrapher)
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, select

from poligrapher_app.api.database import Base
import poligrapher_app.api.models  # noqa: F401
from poligrapher_app.services.storage import AzureBlobStorage


TABLE_ORDER = ("providers", "policies", "schedules", "analysis_results")


def copy_database(source_url: str, target_url: str) -> dict[str, int]:
    source = create_engine(source_url)
    target = create_engine(target_url, pool_pre_ping=True)
    counts: dict[str, int] = {}
    with source.connect() as source_conn, target.begin() as target_conn:
        for name in reversed(TABLE_ORDER):
            target_conn.execute(Base.metadata.tables[name].delete())
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            rows = [dict(row._mapping) for row in source_conn.execute(select(table))]
            if rows:
                target_conn.execute(table.insert(), rows)
            counts[name] = len(rows)
    source.dispose()
    target.dispose()
    return counts


def copy_objects(root: str | Path, storage: AzureBlobStorage) -> int:
    root = Path(root).resolve()
    copied = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        key = path.relative_to(root).as_posix()
        content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/zip"
        storage.upload_file(key, path, content_type=content_type)
        copied += 1
    return copied


def main() -> None:
    target = os.environ.get("TARGET_DATABASE_URL")
    connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not target or not connection:
        raise SystemExit("TARGET_DATABASE_URL and AZURE_STORAGE_CONNECTION_STRING are required")
    storage = AzureBlobStorage(
        connection, os.getenv("AZURE_STORAGE_CONTAINER", "poligrapher")
    )
    objects = 0
    if os.getenv("SKIP_OBJECTS", "false").lower() not in ("1", "true", "yes"):
        objects = copy_objects(os.getenv("LOCAL_STORAGE_ROOT", "./storage"), storage)
    counts = copy_database(
        os.getenv("SOURCE_DATABASE_URL", "sqlite:///./poligrapher.db"), target
    )
    print({"objects": objects, **counts})


if __name__ == "__main__":
    main()
