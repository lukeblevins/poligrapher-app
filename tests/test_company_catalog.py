import io
import json
import tarfile

from poligrapher_app.services import company_catalog


class _Response:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_search_open_terms_returns_privacy_policy_matches(monkeypatch):
    company_catalog._cached_paths = []
    company_catalog._cached_at = 0.0

    def fake_get(url, **_kwargs):
        if "git/trees" in url:
            return _Response(
                {
                    "tree": [
                        {"type": "blob", "path": "declarations/Adobe.json"},
                        {"type": "blob", "path": "declarations/Adobe.history.json"},
                        {"type": "blob", "path": "README.md"},
                    ]
                }
            )
        return _Response(
            {
                "name": "Adobe",
                "terms": {
                    "Privacy Policy": {
                        "fetch": "https://www.adobe.com/privacy/policy.html",
                        "executeClientScripts": True,
                    }
                },
            }
        )

    monkeypatch.setattr(company_catalog.httpx, "get", fake_get)
    results, available = company_catalog.search_open_terms("ado")

    assert available is True
    assert results == [
        {
            "id": "declarations/Adobe.json",
            "name": "Adobe",
            "domain": "adobe.com",
            "source_url": "https://www.adobe.com/privacy/policy.html",
            "source": "open_terms_archive",
            "attribution_url": (
                "https://github.com/OpenTermsArchive/contrib-declarations/"
                "blob/main/declarations/Adobe.json"
            ),
            "requires_javascript": True,
        }
    ]


def test_search_open_terms_fails_softly(monkeypatch):
    company_catalog._cached_paths = []
    company_catalog._cached_at = 0.0

    def fail(*_args, **_kwargs):
        raise company_catalog.httpx.ConnectError("offline")

    monkeypatch.setattr(company_catalog.httpx, "get", fail)
    results, available = company_catalog.search_open_terms("Adobe")
    assert results == []
    assert available is False


def test_verified_catalog_matches_common_names_tickers_and_punctuation():
    cases = {
        "3M": "3M",
        "Coca Cola": "Coca-Cola Company (The)",
        "JP Morgan": "JPMorgan Chase",
        "AAPL": "Apple Inc.",
    }

    for query, expected_name in cases.items():
        results = company_catalog.search_verified_catalog(query)
        assert results[0]["name"] == expected_name
        assert results[0]["source"] == "verified_source_catalog"


def test_verified_catalog_uses_policy_host_as_a_generic_alias():
    results = company_catalog.search_verified_catalog("Google")

    assert results[0]["name"] == "Alphabet Inc. (Class A)"
    assert results[0]["source_url"] == "https://policies.google.com/privacy"


def test_verified_catalog_avoids_short_fuzzy_and_embedded_domain_false_positives():
    results = company_catalog.search_verified_catalog("Apple")

    assert [result["name"] for result in results] == ["Apple Inc."]


def test_combined_catalog_survives_open_terms_failure(monkeypatch):
    monkeypatch.setattr(company_catalog, "search_open_terms", lambda *_args, **_kwargs: ([], False))

    results, available = company_catalog.search_company_catalog("JP Morgan")

    assert available is True
    assert results[0]["name"] == "JPMorgan Chase"
    assert "tickers" not in results[0]


def test_combined_catalog_deduplicates_the_same_policy_source(monkeypatch):
    duplicate = {
        "id": "declarations/Google.json",
        "name": "Google",
        "domain": "policies.google.com",
        "source_url": "https://policies.google.com/privacy",
        "source": "open_terms_archive",
        "attribution_url": "https://example.test/google",
        "requires_javascript": False,
    }
    monkeypatch.setattr(company_catalog, "search_open_terms", lambda *_args, **_kwargs: ([duplicate], True))

    results, _available = company_catalog.search_company_catalog("Google")

    assert [result["source_url"] for result in results].count("https://policies.google.com/privacy") == 1
    assert results[0]["name"] == "Google"


def test_combined_catalog_deduplicates_company_names_across_sources(monkeypatch):
    duplicate = {
        "id": "declarations/Microsoft.json",
        "name": "Microsoft Corporation",
        "domain": "privacy.microsoft.com",
        "source_url": "https://privacy.microsoft.com/en-us/privacystatement",
        "source": "open_terms_archive",
        "attribution_url": "https://example.test/microsoft",
        "requires_javascript": False,
    }
    monkeypatch.setattr(company_catalog, "search_open_terms", lambda *_args, **_kwargs: ([duplicate], True))

    results, _available = company_catalog.search_company_catalog("Microsoft")

    assert [result["name"] for result in results] == ["Microsoft"]


def test_open_terms_archive_is_parsed_without_extracting_files():
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as archive:
        declarations = {
            "snapshot/declarations/Acme.json": {
                "name": "Acme",
                "terms": {"Privacy Policy": {"fetch": "https://acme.example/privacy"}},
            },
            "snapshot/declarations/No Policy.json": {"name": "No Policy", "terms": {}},
        }
        for path, payload in declarations.items():
            data = json.dumps(payload).encode()
            member = tarfile.TarInfo(path)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

    results = company_catalog.parse_open_terms_archive(content.getvalue())

    assert results[0]["entry"]["name"] == "Acme"
    assert results[1]["entry"] is None
    assert results[1]["rejection"] == "no_fetchable_privacy_policy"
