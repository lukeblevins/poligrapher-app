"""Shared utility functions for the API layer."""

import json
from datetime import date


def provider_slug(name: str) -> str:
    """Filesystem-safe slug for a provider's output directory.

    Mirrors the existing convention (spaces → underscores, other characters
    preserved so names like ``S&P_Global`` stay stable) but neutralizes path
    separators and parent references so a malicious provider name can't escape
    the output directory.
    """
    slug = name.strip().replace(" ", "_")
    slug = slug.replace("/", "_").replace("\\", "_").replace("..", "_")
    return slug or "provider"


def best_website_url(policies) -> str | None:
    """Pick the best website URL to prefill a provider's source from its policies.

    Prefers a webpage policy that previously succeeded, then one that at least
    produced a score, then any webpage URL, then any http(s) URL.
    """
    webpages = [p for p in policies if p.source == "webpage" and (p.url or "").lower().startswith("http")]
    for accept in (
        lambda p: p.pipeline_status == "succeeded",
        lambda p: p.privacy_score is not None or p.gdpr_score is not None,
        lambda p: True,
    ):
        for p in webpages:
            if accept(p):
                return p.url
    for p in policies:
        if (p.url or "").lower().startswith("http"):
            return p.url
    return None


def parse_date(val: str) -> date | None:
    try:
        return date.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def parse_pipeline_errors(val) -> list:
    if not val or isinstance(val, float):
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []
