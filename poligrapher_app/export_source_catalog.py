"""Export verified S&P 500 sources as a reproducible deployment snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.api.models import CompanyCollection
from poligrapher_app.services.source_catalog import CATALOG_PATH, CATALOG_VERSION
from poligrapher_app.services.sp500_catalog import COLLECTION_NAME


def main() -> None:
    with SessionLocal() as db:
        collection = db.query(CompanyCollection).filter_by(name=COLLECTION_NAME).one()
        providers = sorted(collection.providers, key=lambda provider: (provider.cik or "", provider.name))
        unavailable = [
            provider.name
            for provider in providers
            if not provider.source_url or provider.source_status != "available"
        ]
        if unavailable:
            raise SystemExit(
                f"Refusing to export: {len(unavailable)} collection sources are not ready"
            )
        sources = [
            {
                "name": provider.name,
                "cik": provider.cik,
                "tickers": provider.tickers or ([provider.ticker] if provider.ticker else []),
                "domain": provider.domain,
                "source_url": provider.source_url,
                "source_status": provider.source_status,
                "source_checked_at": (
                    provider.source_checked_at.isoformat()
                    if provider.source_checked_at
                    else None
                ),
                "source_http_status": provider.source_http_status,
                "source_final_url": provider.source_final_url,
            }
            for provider in providers
        ]

    payload = {
        "version": CATALOG_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": COLLECTION_NAME,
        "sources": sources,
    }
    path = Path(CATALOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print({"path": str(path), "sources": len(sources)})


if __name__ == "__main__":
    main()
