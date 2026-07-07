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
