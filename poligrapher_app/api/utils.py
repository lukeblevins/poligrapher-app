"""Shared utility functions for the API layer."""

import json
from datetime import date


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
