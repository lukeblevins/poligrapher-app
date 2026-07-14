"""Graph presentation services.

Turns a policy's knowledge-graph artifacts into JSON the frontend can render
directly (cytoscape elements, statistics, structured GDPR report). No styling or
HTML lives here — the React ``GraphViewer`` owns all view concerns.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poligrapher_app.domain.policy_analysis import PolicyDocumentInfo

# Research questions, in display order, for grouping GDPR violations.
_RQ_ORDER = ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6")


def build_cytoscape_elements(policy: PolicyDocumentInfo) -> list[dict]:
    """Return cytoscape.js ``elements`` for the policy's knowledge graph.

    Reads ``graph-original.full.yml`` (NetworkX node-link data) and maps nodes /
    links onto cytoscape element dicts. Returns an empty list if the YAML is
    missing. Styling/theming is applied client-side.
    """
    yml_file = os.path.join(policy.output_dir, "graph-original.full.yml")
    if not os.path.exists(yml_file):
        return []

    import yaml

    with open(yml_file, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    elements: list[dict] = []
    for node in data.get("nodes", []):
        node_id = node["id"]
        elements.append(
            {"data": {"id": node_id, "label": node_id, "type": node.get("type", "DATA")}}
        )

    for i, link in enumerate(data.get("links", [])):
        elements.append(
            {
                "data": {
                    "id": f"e{i}",
                    "source": link["source"],
                    "target": link["target"],
                    "label": link.get("key", ""),
                }
            }
        )

    return elements


def graph_statistics(policy: PolicyDocumentInfo) -> dict | None:
    """Return the graph summary statistics dict, or None if no graph exists."""
    if not policy.has_graph():
        return None
    return policy.get_graph_statistics()


def gdpr_report(result: dict | None) -> dict | None:
    """Build a structured GDPR report from a raw ``policy_scorer`` result dict.

    Returns None when there is no result. On failure results, returns a minimal
    payload with ``success=False`` and the feedback messages.
    """
    if not result:
        return None
    if not result.get("success"):
        return {"success": False, "feedback": result.get("feedback", [])}

    grouped = result.get("violations_by_rq", {}) or {}
    top_violations = {
        rq: grouped[rq][:3] for rq in _RQ_ORDER if grouped.get(rq)
    }

    return {
        "success": True,
        "total_score": result.get("total_score", 0),
        "normalized_score": result.get("normalized_score", 0),
        "tier": result.get("tier", "UNKNOWN"),
        "summary": result.get("summary", ""),
        "component_scores": result.get("component_scores", {}),
        "severity_counts": result.get("severity_counts", {}),
        "flags": result.get("flags", []),
        "feature_summary": result.get("feature_summary", {}),
        "top_violations": top_violations,
    }


def readability_from_gdpr(result: dict | None) -> dict | None:
    """Extract readability metrics from a GDPR result's ``feature_summary``."""
    if not result or not result.get("success"):
        return None
    fs = result.get("feature_summary") or {}
    if not fs:
        return None
    return {
        "flesch_kincaid": fs.get("flesch_kincaid", 0),
        "gunning_fog": fs.get("gunning_fog", 0),
        "flesch_reading_ease": fs.get("flesch_reading_ease", 0),
        "n_words": fs.get("n_words", 0),
        "n_sentences": fs.get("n_sentences", 0),
        "passive_ratio": fs.get("passive_ratio", 0),
    }
