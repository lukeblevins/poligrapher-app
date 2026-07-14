"""Synchronize a current S&P 500 issuer collection from an open constituent list."""

from __future__ import annotations

import csv
import io
import re
from datetime import date

import httpx
from sqlalchemy.orm import Session

from poligrapher_app.api.models import CompanyCollection, Provider
from poligrapher_app.services.acquisition import registrable_domain

DATA_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
COLLECTION_NAME = "S&P 500"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"


def _name_key(value: str) -> str:
    value = re.sub(r"\([^)]*class[^)]*\)", "", value, flags=re.I)
    value = value.replace("&", "and")
    value = re.sub(r"\b(the|incorporated|inc|corporation|corp|company|co|plc|limited|ltd)\b", "", value, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def fetch_constituents() -> list[dict[str, str]]:
    response = httpx.get(DATA_URL, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(response.text)))
    required = {"Symbol", "Security", "GICS Sector", "CIK"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("S&P 500 constituent source returned an unexpected schema")
    return rows


def _official_domains(ciks: list[str]) -> dict[str, str]:
    """Return official-site domains from Wikidata; failure is deliberately soft."""
    results: dict[str, str] = {}
    headers = {"User-Agent": "privacy-policy-research/1.0 (company metadata sync)"}
    for offset in range(0, len(ciks), 100):
        values = " ".join(f'"{cik.zfill(10)}"' for cik in ciks[offset:offset + 100])
        query = f"""
            SELECT ?cik ?website WHERE {{
              VALUES ?cik {{ {values} }}
              ?item wdt:P5531 ?cik; wdt:P856 ?website.
            }}
        """
        try:
            response = httpx.post(
                WIKIDATA_ENDPOINT,
                data={"query": query, "format": "json"},
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
        except (httpx.HTTPError, ValueError):
            continue
        for binding in bindings:
            cik = binding.get("cik", {}).get("value", "").lstrip("0") or "0"
            website = binding.get("website", {}).get("value", "")
            domain = registrable_domain(website)
            if domain:
                results.setdefault(cik, domain)
    return results


def sync_sp500(
    db: Session,
    rows: list[dict[str, str]] | None = None,
    *,
    enrich_domains: bool = True,
) -> dict:
    """Upsert current issuers and replace the system collection membership."""
    rows = rows or fetch_constituents()
    collection = db.query(CompanyCollection).filter_by(name=COLLECTION_NAME).first()
    if collection is None:
        collection = CompanyCollection(
            name=COLLECTION_NAME,
            description="Current S&P 500 constituent companies, deduplicated by SEC CIK.",
            kind="system",
            source_url=DATA_URL,
        )
        db.add(collection)
        db.flush()

    providers = db.query(Provider).all()
    by_cik = {p.cik: p for p in providers if p.cik}
    by_ticker = {ticker: p for p in providers for ticker in (p.tickers or ([p.ticker] if p.ticker else []))}
    by_name = {_name_key(p.name): p for p in providers}

    created = updated = 0
    members: list[Provider] = []
    seen_ids = set()
    for row in rows:
        symbol = row["Symbol"].strip()
        cik = row["CIK"].strip().lstrip("0") or None
        name = row["Security"].strip()
        provider = (
            (by_cik.get(cik) if cik else None)
            or by_ticker.get(symbol)
            or by_name.get(_name_key(name))
        )
        if provider is None:
            provider = Provider(name=name, industry=row["GICS Sector"].strip() or None)
            db.add(provider)
            db.flush()
            providers.append(provider)
            created += 1
        else:
            updated += 1

        symbols = list(dict.fromkeys([*(provider.tickers or []), symbol]))
        provider.tickers = symbols
        provider.ticker = provider.ticker or symbol
        provider.cik = provider.cik or cik
        provider.industry = row["GICS Sector"].strip() or provider.industry
        if cik:
            by_cik[cik] = provider
        by_ticker[symbol] = provider
        by_name[_name_key(name)] = provider
        if provider.id not in seen_ids:
            members.append(provider)
            seen_ids.add(provider.id)

    collection.providers = members
    collection.kind = "system"
    collection.source_url = DATA_URL
    collection.snapshot_date = date.today()
    if enrich_domains:
        domains = _official_domains([provider.cik for provider in members if provider.cik and not provider.domain])
        for provider in members:
            if not provider.domain and provider.cik in domains:
                provider.domain = domains[provider.cik]
    db.commit()
    db.refresh(collection)
    return {
        "collection_id": collection.id,
        "securities": len(rows),
        "companies": len(members),
        "created": created,
        "updated": updated,
        "snapshot_date": collection.snapshot_date,
    }
