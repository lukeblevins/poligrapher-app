"""Build a deterministic, read-only company-analysis cohort manifest."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from typing import Iterable

import httpx

from poligrapher_app.services.company_catalog import (
    catalog_identity_keys,
    download_open_terms_catalog,
    open_terms_snapshot,
    parse_open_terms_archive,
    verified_catalog_entries,
)
from poligrapher_app.services.source_catalog import CATALOG_PATH

DEFAULT_SEED = 20260817
DEFAULT_SIZE = 50


def _existing_keys(providers: Iterable[dict]) -> tuple[set[str], set[str], set[str]]:
    names: set[str] = set()
    domains: set[str] = set()
    sources: set[str] = set()
    for provider in providers:
        name, provider_domains, source = catalog_identity_keys(provider)
        names.add(name)
        domains.update(provider_domains)
        if source:
            sources.add(source)
    return names, domains, sources


def _exclusion_reason(
    entry: dict,
    names: set[str],
    domains: set[str],
    sources: set[str],
    *,
    prefix: str,
) -> str | None:
    name, entry_domains, source = catalog_identity_keys(entry)
    if name in names:
        return f"{prefix}_name"
    if source and source in sources:
        return f"{prefix}_policy_source"
    if entry_domains & domains:
        return f"{prefix}_domain"
    return None


def build_manifest(
    *,
    existing_providers: list[dict],
    verified_entries: list[dict],
    open_terms_results: list[dict],
    size: int = DEFAULT_SIZE,
    seed: int = DEFAULT_SEED,
    ota_tree_sha: str | None = None,
    ota_archive_sha256: str | None = None,
    verified_generated_at: str | None = None,
    existing_source: str = "unspecified",
) -> dict:
    """Deduplicate the complete eligible universe, then sample uniformly."""

    if size < 1:
        raise ValueError("Cohort size must be positive")
    existing_names, existing_domains, existing_sources = _existing_keys(existing_providers)
    eligible: list[dict] = []
    rejections: list[dict] = []
    sampled_names: set[str] = set()
    sampled_domains: set[str] = set()
    sampled_sources: set[str] = set()

    raw_entries = [
        *verified_entries,
        *(item["entry"] for item in open_terms_results if item.get("entry") is not None),
    ]
    raw_entries.sort(key=lambda entry: (entry["source"] != "verified_source_catalog", entry["id"]))
    for entry in raw_entries:
        reason = _exclusion_reason(
            entry,
            existing_names,
            existing_domains,
            existing_sources,
            prefix="existing",
        ) or _exclusion_reason(
            entry,
            sampled_names,
            sampled_domains,
            sampled_sources,
            prefix="catalog_duplicate",
        )
        if reason:
            rejections.append({"id": entry["id"], "name": entry["name"], "reason": reason})
            continue
        name, entry_domains, source = catalog_identity_keys(entry)
        sampled_names.add(name)
        sampled_domains.update(entry_domains)
        if source:
            sampled_sources.add(source)
        cleaned = dict(entry)
        cleaned.pop("tickers", None)
        eligible.append(cleaned)

    for result in open_terms_results:
        if result.get("entry") is None:
            rejections.append({
                "id": result["path"],
                "name": None,
                "reason": result.get("rejection") or "unknown_catalog_error",
            })

    if len(eligible) < size:
        raise ValueError(f"Only {len(eligible)} unique new companies are eligible; need {size}")
    eligible.sort(key=lambda entry: entry["id"])
    rng = random.Random(seed)
    rng.shuffle(eligible)
    selected = eligible[:size]
    for position, entry in enumerate(selected, start=1):
        entry["sample_position"] = position

    eligible_digest = hashlib.sha256(
        json.dumps(
            [{"id": item["id"], "source_url": item["source_url"]} for item in sorted(eligible, key=lambda item: item["id"])],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    rejection_counts = Counter(item["reason"] for item in rejections)
    return {
        "schema_version": 1,
        "dry_run": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "requested_size": size,
        "existing_provider_source": existing_source,
        "snapshots": {
            "open_terms_tree_sha": ota_tree_sha,
            "open_terms_archive_sha256": ota_archive_sha256,
            "verified_catalog_generated_at": verified_generated_at,
            "eligible_universe_sha256": eligible_digest,
        },
        "counts": {
            "existing_providers": len(existing_providers),
            "verified_catalog_entries": len(verified_entries),
            "open_terms_declarations": len(open_terms_results),
            "eligible_unique_new_companies": len(eligible),
            "selected": len(selected),
            "rejected": len(rejections),
            "rejections_by_reason": dict(sorted(rejection_counts.items())),
        },
        "selected": selected,
        "rejections": rejections,
    }


def fetch_existing_providers(api_base_url: str) -> list[dict]:
    response = httpx.get(
        f"{api_base_url.rstrip('/')}/api/providers",
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Provider API returned an unexpected response")
    return payload


def generate_manifest(
    *,
    api_base_url: str | None,
    existing_providers_path: Path | None,
    open_terms_archive_path: Path | None,
    size: int,
    seed: int,
) -> dict:
    if existing_providers_path:
        providers = json.loads(existing_providers_path.read_text(encoding="utf-8"))
        existing_source = str(existing_providers_path)
    elif api_base_url:
        providers = fetch_existing_providers(api_base_url)
        existing_source = api_base_url.rstrip("/")
    else:
        raise ValueError("Either an API base URL or existing-provider snapshot is required")
    if not isinstance(providers, list):
        raise ValueError("Existing-provider snapshot must contain a JSON list")

    archive_digest = None
    if open_terms_archive_path:
        archive_content = open_terms_archive_path.read_bytes()
        archive_digest = hashlib.sha256(archive_content).hexdigest()
        open_terms = parse_open_terms_archive(archive_content)
        tree_sha = None
    else:
        paths, tree_sha = open_terms_snapshot()
        open_terms = download_open_terms_catalog(tree_sha)
        loaded_paths = {item["path"] for item in open_terms}
        for missing_path in sorted(set(paths) - loaded_paths):
            open_terms.append({"path": missing_path, "entry": None, "rejection": "archive_missing_entry"})
    verified_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return build_manifest(
        existing_providers=providers,
        verified_entries=verified_catalog_entries(),
        open_terms_results=open_terms,
        size=size,
        seed=seed,
        ota_tree_sha=tree_sha,
        ota_archive_sha256=archive_digest,
        verified_generated_at=verified_payload.get("generated_at"),
        existing_source=existing_source,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    provider_source = parser.add_mutually_exclusive_group(required=True)
    provider_source.add_argument("--api-base-url")
    provider_source.add_argument("--existing-providers-json", type=Path)
    parser.add_argument("--open-terms-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--dry-run", action="store_true", help="Required safety acknowledgement")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("--dry-run is required; this command never creates companies or collections")
    manifest = generate_manifest(
        api_base_url=args.api_base_url,
        existing_providers_path=args.existing_providers_json,
        open_terms_archive_path=args.open_terms_archive,
        size=args.size,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": manifest["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
