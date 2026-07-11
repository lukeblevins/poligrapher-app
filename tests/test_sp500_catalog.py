from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import CompanyCollection, Provider
from poligrapher_app.services.sp500_catalog import sync_sp500


def test_sp500_sync_deduplicates_share_classes_and_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    rows = [
        {"Symbol": "GOOGL", "Security": "Alphabet Inc. (Class A)", "GICS Sector": "Communication Services", "CIK": "1652044"},
        {"Symbol": "GOOG", "Security": "Alphabet Inc. (Class C)", "GICS Sector": "Communication Services", "CIK": "1652044"},
        {"Symbol": "AFL", "Security": "Aflac", "GICS Sector": "Financials", "CIK": "4977"},
    ]
    with Session(engine) as db:
        existing = Provider(name="Aflac", source_url="https://example.com/privacy")
        db.add(existing)
        db.commit()

        first = sync_sp500(db, rows, enrich_domains=False)
        second = sync_sp500(db, rows, enrich_domains=False)

        assert first["securities"] == 3
        assert first["companies"] == 2
        assert first["created"] == 1
        assert second["created"] == 0
        assert db.query(Provider).count() == 2
        alphabet = db.query(Provider).filter_by(cik="1652044").one()
        assert alphabet.tickers == ["GOOGL", "GOOG"]
        collection = db.query(CompanyCollection).filter_by(name="S&P 500").one()
        assert len(collection.providers) == 2
