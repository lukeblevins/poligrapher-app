import pytest

from poligrapher_app.experiments.apply_catalog_cohort import (
    collection_description,
    plan_application,
)


def _manifest(*selected):
    return {
        "schema_version": 1,
        "seed": 7,
        "requested_size": len(selected),
        "snapshots": {"eligible_universe_sha256": "abc123"},
        "selected": list(selected),
    }


def _entry(name, domain):
    return {
        "id": f"catalog:{name}",
        "name": name,
        "domain": domain,
        "source_url": f"https://{domain}/privacy",
        "source": "open_terms_archive",
    }


def test_apply_plan_creates_missing_providers_and_collection():
    manifest = _manifest(_entry("Alpha", "alpha.com"), _entry("Bravo", "bravo.com"))

    plan = plan_application(manifest, [], [], "Pilot")

    assert [item["name"] for item in plan["create"]] == ["Alpha", "Bravo"]
    assert plan["reuse"] == []
    assert plan["conflicts"] == []
    assert plan["collection"] == {"action": "create"}


def test_apply_plan_resumes_with_existing_provider_and_owned_collection():
    selected = _entry("Alpha", "alpha.com")
    manifest = _manifest(selected)
    description = collection_description(manifest)
    providers = [{**selected, "id": "provider-1"}]
    collections = [{"id": "collection-1", "name": "Pilot", "description": description}]

    plan = plan_application(manifest, providers, collections, "Pilot")

    assert plan["create"] == []
    assert plan["reuse"][0]["provider_id"] == "provider-1"
    assert plan["collection"] == {"action": "update", "collection_id": "collection-1"}


def test_apply_plan_refuses_a_different_company_on_an_existing_parent_domain():
    manifest = _manifest(_entry("Product", "example.com"))
    providers = [{
        "id": "provider-1",
        "name": "Parent",
        "domain": "www.example.com",
        "source_url": "https://example.com/privacy",
    }]

    plan = plan_application(manifest, providers, [], "Pilot")

    assert plan["create"] == []
    assert plan["conflicts"][0]["reason"] == "existing_policy_source"


def test_apply_plan_refuses_an_incomplete_manifest():
    manifest = _manifest(_entry("Alpha", "alpha.com"))
    manifest["requested_size"] = 2

    with pytest.raises(ValueError, match="Manifest selection is incomplete"):
        plan_application(manifest, [], [], "Pilot")
