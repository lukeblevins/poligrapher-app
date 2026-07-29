import pytest
from pydantic import ValidationError

from poligrapher_app.api.schemas import ProviderCreate
from poligrapher_app.domain.industries import INDUSTRIES, normalize_industry


def test_industries_are_the_eleven_gics_sectors():
    assert len(INDUSTRIES) == 11
    assert "Health Care" in INDUSTRIES
    assert "Information Technology" in INDUSTRIES


def test_industry_normalization_handles_empty_case_and_legacy_spelling():
    assert normalize_industry(None) is None
    assert normalize_industry(" ") is None
    assert normalize_industry("financials") == "Financials"
    assert normalize_industry("Healthcare") == "Health Care"


def test_provider_create_rejects_nonstandard_industry():
    with pytest.raises(ValidationError, match="Industry must be one of"):
        ProviderCreate(name="Example", industry="Technology")
