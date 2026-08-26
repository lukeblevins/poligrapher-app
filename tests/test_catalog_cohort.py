import pytest

from poligrapher_app.experiments.catalog_cohort import build_manifest


def _entry(name, *, source="open_terms_archive", domain=None, url=None):
    slug = name.casefold().replace(" ", "-")
    return {
        "id": f"{source}:{slug}",
        "name": name,
        "domain": domain or f"{slug}.com",
        "source_url": url or f"https://{slug}.com/privacy",
        "source": source,
        "attribution_url": f"https://catalog.example/{slug}",
        "requires_javascript": False,
    }


def _ota(*entries, rejection=None):
    results = [
        {"path": entry["id"], "entry": entry, "rejection": None}
        for entry in entries
    ]
    if rejection:
        results.append({"path": "declarations/Unavailable.json", "entry": None, "rejection": rejection})
    return results


def test_manifest_is_seeded_and_excludes_existing_and_duplicate_companies():
    existing = [{"name": "Alpha Inc.", "domain": "alpha.com", "source_url": None}]
    verified = [
        _entry("Alpha", source="verified_source_catalog"),
        _entry("Bravo", source="verified_source_catalog"),
    ]
    open_terms = _ota(
        _entry("Bravo Corporation", url="https://other.com/privacy"),
        _entry("Charlie"),
        _entry("Delta"),
        rejection="no_fetchable_privacy_policy",
    )

    first = build_manifest(
        existing_providers=existing,
        verified_entries=verified,
        open_terms_results=open_terms,
        size=2,
        seed=42,
    )
    second = build_manifest(
        existing_providers=existing,
        verified_entries=verified,
        open_terms_results=open_terms,
        size=2,
        seed=42,
    )

    assert [item["id"] for item in first["selected"]] == [
        item["id"] for item in second["selected"]
    ]
    assert first["counts"]["eligible_unique_new_companies"] == 3
    assert first["counts"]["rejections_by_reason"] == {
        "catalog_duplicate_name": 1,
        "existing_name": 1,
        "no_fetchable_privacy_policy": 1,
    }


def test_manifest_changes_selection_with_seed_but_not_eligible_digest():
    entries = [_entry(name) for name in ("Alpha", "Bravo", "Charlie", "Delta", "Echo")]
    first = build_manifest(
        existing_providers=[],
        verified_entries=[],
        open_terms_results=_ota(*entries),
        size=3,
        seed=1,
    )
    second = build_manifest(
        existing_providers=[],
        verified_entries=[],
        open_terms_results=_ota(*entries),
        size=3,
        seed=2,
    )

    assert [item["id"] for item in first["selected"]] != [
        item["id"] for item in second["selected"]
    ]
    assert first["snapshots"]["eligible_universe_sha256"] == (
        second["snapshots"]["eligible_universe_sha256"]
    )


def test_manifest_refuses_an_undersized_eligible_universe():
    with pytest.raises(ValueError, match="Only 1 unique new companies are eligible; need 2"):
        build_manifest(
            existing_providers=[],
            verified_entries=[],
            open_terms_results=_ota(_entry("Alpha")),
            size=2,
            seed=1,
        )


def test_manifest_excludes_services_owned_by_an_existing_parent_domain():
    existing = [{
        "name": "Alphabet",
        "domain": "abc.xyz",
        "source_url": "https://policies.google.com/privacy",
    }]
    waze = _entry(
        "Waze",
        domain="support.google.com",
        url="https://support.google.com/waze/privacy",
    )

    with pytest.raises(ValueError, match="Only 0 unique new companies are eligible; need 1"):
        build_manifest(
            existing_providers=existing,
            verified_entries=[],
            open_terms_results=_ota(waze),
            size=1,
            seed=1,
        )
