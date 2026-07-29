"""Canonical company industry taxonomy.

The application uses the GICS sector level: it is broad enough to apply to
every company while remaining stable and compatible with the S&P 500 catalog.
"""

INDUSTRIES = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

_ALIASES = {
    "healthcare": "Health Care",
}


def normalize_industry(value: str | None) -> str | None:
    """Return a canonical industry, or reject values outside the taxonomy."""
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    canonical = _ALIASES.get(candidate.casefold())
    if canonical:
        return canonical
    for industry in INDUSTRIES:
        if candidate.casefold() == industry.casefold():
            return industry
    raise ValueError(f"Industry must be one of: {', '.join(INDUSTRIES)}")
