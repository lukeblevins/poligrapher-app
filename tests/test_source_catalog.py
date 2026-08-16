import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Provider
from poligrapher_app.services.source_catalog import (
    CATALOG_PATH,
    apply_source_catalog,
    load_source_catalog,
)


def _source(**overrides):
    source = {
        "name": "3M",
        "cik": "66740",
        "tickers": ["MMM"],
        "domain": "3m.com",
        "source_url": "https://www.3m.com/privacy",
        "source_status": "available",
        "source_checked_at": "2026-07-28T04:00:00+00:00",
        "source_http_status": 200,
        "source_final_url": "https://www.3m.com/privacy",
    }
    source.update(overrides)
    return source


def test_load_source_catalog_validates_version(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"version": 2, "sources": []}))

    try:
        load_source_catalog(path)
    except ValueError as error:
        assert "Unsupported source catalog version" in str(error)
    else:
        raise AssertionError("A mismatched catalog version should fail")


def test_packaged_sp500_catalog_contains_500_ready_sources():
    sources = load_source_catalog(CATALOG_PATH)

    assert len(sources) == 500
    assert all(source["source_url"] for source in sources)
    assert all(source["source_status"] == "available" for source in sources)


def test_packaged_sp500_catalog_keeps_reviewed_source_replacements():
    sources = {source["name"]: source for source in load_source_catalog(CATALOG_PATH)}

    assert sources["Amazon"]["source_url"].startswith(
        "https://www.amazon.com/gp/help/customer/display.html"
    )
    assert sources["Ametek"]["source_url"] == "https://www.ametek.com/privacy"
    assert sources["Ameriprise Financial"]["source_url"] == (
        "https://www.ameriprise.com/privacy-security-fraud"
    )
    assert sources["American Water Works"]["source_url"].endswith(
        "/American-Water-Privacy-Policy.pdf"
    )
    assert sources["Fortive"]["source_url"] == (
        "https://fortive.com/global-privacy-policy"
    )
    assert sources["Tyson Foods"]["source_url"] == (
        "https://www.tysonfoods.com/legal/privacy-policy"
    )
    assert sources["Xcel Energy"]["source_url"].endswith("/Privacy%20Notice.pdf")
    assert sources["Extra Space Storage"]["source_url"] == (
        "https://www.extraspace.com/help/privacy/"
    )
    assert sources["Ralph Lauren Corporation"]["source_url"].endswith(
        "/privacy-policy/privacy-policy.html"
    )
    assert sources["United Rentals"]["source_url"] == (
        "https://www.unitedrentals.com/legal/privacy-policy"
    )


def test_apply_source_catalog_updates_matching_provider():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(name="3M", ticker="MMM", tickers=["MMM"], cik="66740")
        db.add(provider)
        db.commit()

        summary = apply_source_catalog(db, [_source()])

        db.refresh(provider)
        assert summary.updated == 1
        assert provider.source_status == "available"
        assert provider.source_http_status == 200
        assert provider.source_url == "https://www.3m.com/privacy"


def test_apply_source_catalog_preserves_newer_production_check():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(
            name="3M",
            ticker="MMM",
            tickers=["MMM"],
            cik="66740",
            source_url="https://new.example/privacy",
            source_status="available",
            source_checked_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
        db.add(provider)
        db.commit()

        summary = apply_source_catalog(db, [_source()])

        db.refresh(provider)
        assert summary.newer_preserved == 1
        assert provider.source_url == "https://new.example/privacy"


def test_apply_source_catalog_rolls_back_if_provider_is_missing():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        try:
            apply_source_catalog(db, [_source()])
        except ValueError as error:
            assert "did not match 1 providers" in str(error)
        else:
            raise AssertionError("A missing provider should fail the deployment import")
