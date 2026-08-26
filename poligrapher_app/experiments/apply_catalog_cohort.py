"""Idempotently create providers and a collection from a frozen cohort manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx

from poligrapher_app.services.company_catalog import catalog_identity_keys


def collection_description(manifest: dict) -> str:
    digest = manifest["snapshots"]["eligible_universe_sha256"]
    return (
        "Reproducible random company analysis pilot; "
        f"seed={manifest['seed']}; eligible_universe_sha256={digest}; "
        f"manifest_schema={manifest['schema_version']}."
    )


def plan_application(
    manifest: dict,
    existing_providers: list[dict],
    existing_collections: list[dict],
    collection_name: str,
) -> dict:
    """Describe an idempotent apply and reject ambiguous identity collisions."""

    if len(manifest.get("selected") or []) != manifest.get("requested_size"):
        raise ValueError("Manifest selection is incomplete")
    providers_by_name: dict[str, list[dict]] = {}
    providers_by_source: dict[str, list[dict]] = {}
    provider_domains: dict[str, list[dict]] = {}
    for provider in existing_providers:
        name, domains, source = catalog_identity_keys(provider)
        providers_by_name.setdefault(name, []).append(provider)
        if source:
            providers_by_source.setdefault(source, []).append(provider)
        for domain in domains:
            provider_domains.setdefault(domain, []).append(provider)

    create: list[dict] = []
    reuse: list[dict] = []
    conflicts: list[dict] = []
    for selected in manifest["selected"]:
        name, domains, source = catalog_identity_keys(selected)
        exact = providers_by_name.get(name, [])
        same_source = providers_by_source.get(source, []) if source else []
        if len(exact) == 1:
            provider = exact[0]
            reuse.append({"selected": selected, "provider_id": provider["id"]})
            continue
        if len(exact) > 1:
            conflicts.append({"selected": selected, "reason": "ambiguous_existing_identity"})
            continue
        if same_source:
            conflicts.append({
                "selected": selected,
                "reason": "existing_policy_source",
                "matching_provider_ids": sorted(item["id"] for item in same_source),
            })
            continue
        domain_matches = {
            item["id"]: item
            for domain in domains
            for item in provider_domains.get(domain, [])
        }
        if domain_matches:
            conflicts.append({
                "selected": selected,
                "reason": "existing_parent_domain",
                "matching_provider_ids": sorted(domain_matches),
            })
            continue
        create.append(selected)

    description = collection_description(manifest)
    named_collections = [item for item in existing_collections if item["name"] == collection_name]
    if len(named_collections) > 1:
        collection_action = {"action": "conflict", "reason": "duplicate_collection_names"}
    elif named_collections:
        collection = named_collections[0]
        collection_action = (
            {"action": "update", "collection_id": collection["id"]}
            if collection.get("description") == description
            else {"action": "conflict", "reason": "collection_name_in_use"}
        )
    else:
        collection_action = {"action": "create"}
    return {
        "collection_name": collection_name,
        "collection_description": description,
        "create": create,
        "reuse": reuse,
        "conflicts": conflicts,
        "collection": collection_action,
    }


def _request(client: httpx.Client, method: str, path: str, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None


def apply_manifest(api_base_url: str, manifest: dict, collection_name: str) -> dict:
    """Apply a manifest through public APIs; safe to resume after interruption."""

    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=30.0, follow_redirects=True) as client:
        providers = _request(client, "GET", "/api/providers")
        collections = _request(client, "GET", "/api/collections")
        plan = plan_application(manifest, providers, collections, collection_name)
        if plan["conflicts"] or plan["collection"]["action"] == "conflict":
            raise ValueError("Apply plan contains identity or collection conflicts")

        provider_ids_by_catalog_id = {
            item["selected"]["id"]: item["provider_id"]
            for item in plan["reuse"]
        }
        created: list[dict] = []
        for selected in plan["create"]:
            provider = _request(client, "POST", "/api/providers", json={
                "name": selected["name"],
                "domain": selected.get("domain"),
                "source_url": selected["source_url"],
                "industry": None,
            })
            provider_ids_by_catalog_id[selected["id"]] = provider["id"]
            created.append({"provider_id": provider["id"], "name": provider["name"]})

        provider_ids = [
            provider_ids_by_catalog_id[selected["id"]]
            for selected in manifest["selected"]
        ]

        body = {
            "name": collection_name,
            "description": plan["collection_description"],
            "provider_ids": provider_ids,
        }
        if plan["collection"]["action"] == "create":
            collection = _request(client, "POST", "/api/collections", json=body)
        else:
            collection = _request(
                client,
                "PATCH",
                f"/api/collections/{plan['collection']['collection_id']}",
                json={"description": body["description"], "provider_ids": provider_ids},
            )
    return {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "created": created,
        "reused": plan["reuse"],
        "collection": collection,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--apply", action="store_true", help="Perform writes; otherwise print a preview")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.apply:
        result = apply_manifest(args.api_base_url, manifest, args.collection_name)
    else:
        providers = httpx.get(
            f"{args.api_base_url.rstrip('/')}/api/providers",
            timeout=30.0,
            follow_redirects=True,
        )
        providers.raise_for_status()
        collections = httpx.get(
            f"{args.api_base_url.rstrip('/')}/api/collections",
            timeout=30.0,
            follow_redirects=True,
        )
        collections.raise_for_status()
        result = plan_application(
            manifest,
            providers.json(),
            collections.json(),
            args.collection_name,
        )
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
