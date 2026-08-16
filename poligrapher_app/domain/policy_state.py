"""Shared predicates for interpreting persisted policy-analysis state."""

from __future__ import annotations

from typing import Any


def has_graph_elements(graph_data: Any) -> bool:
    """Return whether persisted graph data represents a completed analysis."""

    return isinstance(graph_data, dict) and bool(graph_data.get("elements"))
