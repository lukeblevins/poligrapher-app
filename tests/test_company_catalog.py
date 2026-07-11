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
