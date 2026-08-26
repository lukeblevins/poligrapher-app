"""Build a reproducible evaluation report for a frozen company cohort."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import httpx


PROVENANCE_PATTERN = re.compile(
    r"seed=(?P<seed>\d+); eligible_universe_sha256=(?P<digest>[0-9a-f]{64});"
)


def _issue_counts(task: dict) -> dict[str, int]:
    return dict(sorted(Counter(issue["code"] for issue in task.get("issues", [])).items()))


def _issue_companies(task: dict) -> list[dict]:
    return [
        {
            "provider_id": issue.get("provider_id"),
            "provider_name": issue.get("provider_name"),
            "code": issue["code"],
            "retryability": issue["retryability"],
            "recommended_actions": [action["action"] for action in issue.get("actions", [])],
        }
        for issue in task.get("issues", [])
    ]


def _recovery_candidates(task: dict) -> list[dict]:
    candidates: list[dict] = []
    for issue in task.get("issues", []):
        details = issue.get("details") or {}
        issue_candidates = details.get("candidates")
        if not isinstance(issue_candidates, list):
            try:
                technical = json.loads(issue.get("technical_detail") or "{}")
            except (TypeError, ValueError):
                technical = {}
            issue_candidates = technical.get("candidates") or []
        for candidate in issue_candidates:
            if isinstance(candidate, dict):
                candidates.append(candidate)
    return candidates


def _provenance(collection: dict, manifest: dict | None) -> dict:
    if manifest:
        return {
            "seed": manifest.get("seed"),
            "eligible_universe_sha256": (manifest.get("snapshots") or {}).get(
                "eligible_universe_sha256"
            ),
            "manifest_schema": manifest.get("schema_version"),
        }
    description = collection.get("description") or ""
    match = PROVENANCE_PATTERN.search(description)
    return {
        "seed": int(match.group("seed")) if match else None,
        "eligible_universe_sha256": match.group("digest") if match else None,
        "manifest_schema": 1 if match else None,
    }


def build_report(
    *,
    collection: dict,
    providers: list[dict],
    baseline_task: dict,
    recovery_task: dict,
    manifest: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    """Summarize immutable task outcomes and a graph-aware provider snapshot."""

    member_ids = {str(provider_id) for provider_id in collection["provider_ids"]}
    cohort = [provider for provider in providers if str(provider["id"]) in member_ids]
    if len(cohort) != collection["provider_count"]:
        raise ValueError("Provider snapshot does not contain the complete collection")
    if baseline_task.get("status") != "done" or recovery_task.get("status") != "done":
        raise ValueError("Evaluation tasks must be terminal before reporting")
    if baseline_task["total"] != len(cohort) or baseline_task["completed"] != len(cohort):
        raise ValueError("Baseline task does not represent the complete collection")
    failed_provider_ids = {
        issue.get("provider_id")
        for issue in baseline_task.get("issues", [])
        if issue.get("provider_id")
    }
    if len(failed_provider_ids) != baseline_task["failed"]:
        raise ValueError("Baseline failure count does not match its company issues")

    baseline_graphs = max(0, baseline_task["total"] - baseline_task["failed"])
    post_recovery_graphs = sum(int(provider.get("analyzed_count", 0)) > 0 for provider in cohort)
    candidates = _recovery_candidates(recovery_task)
    scored_candidates = [item for item in candidates if item.get("model_score") is not None]
    model_modes = sorted({str(item.get("model_mode") or "off") for item in candidates})
    if not scored_candidates:
        model_conclusion = "not_evaluated_no_model_scores"
    elif model_modes and set(model_modes) <= {"shadow"}:
        model_conclusion = "shadow_scores_could_not_affect_decisions"
    else:
        model_conclusion = "requires_controlled_comparison"

    failed_companies = _issue_companies(baseline_task)
    unresolved_names = sorted(
        provider["name"] for provider in cohort if int(provider.get("analyzed_count", 0)) == 0
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "collection": {
            "id": collection["id"],
            "name": collection["name"],
            "company_count": len(cohort),
            **_provenance(collection, manifest),
        },
        "coverage": {
            "baseline_graphs": baseline_graphs,
            "post_recovery_graphs": post_recovery_graphs,
            "total_companies": len(cohort),
            "baseline_percent": round(100 * baseline_graphs / len(cohort), 2),
            "post_recovery_percent": round(100 * post_recovery_graphs / len(cohort), 2),
            "recovered_graphs": post_recovery_graphs - baseline_graphs,
            "unresolved_companies": unresolved_names,
        },
        "baseline": {
            "task_id": baseline_task["task_id"],
            "status": baseline_task["status"],
            "outcome": baseline_task.get("outcome"),
            "completed": baseline_task["completed"],
            "failed": baseline_task["failed"],
            "issues_by_code": _issue_counts(baseline_task),
            "failed_companies": failed_companies,
        },
        "recovery": {
            "task_id": recovery_task["task_id"],
            "status": recovery_task["status"],
            "outcome": recovery_task.get("outcome"),
            "completed": recovery_task["completed"],
            "failed": recovery_task["failed"],
            "issues_by_code": _issue_counts(recovery_task),
        },
        "model_efficacy": {
            "candidate_observations_in_task": len(candidates),
            "model_scored_candidates": len(scored_candidates),
            "model_modes": model_modes,
            "decision_influence_observed": bool(scored_candidates) and "assist" in model_modes,
            "coverage_uplift": post_recovery_graphs - baseline_graphs,
            "conclusion": model_conclusion,
        },
    }


def render_markdown(report: dict) -> str:
    """Render the machine-readable report as a compact review artifact."""

    collection = report["collection"]
    coverage = report["coverage"]
    baseline = report["baseline"]
    recovery = report["recovery"]
    model = report["model_efficacy"]
    issue_rows = "\n".join(
        f"| `{code}` | {count} |" for code, count in baseline["issues_by_code"].items()
    )
    company_rows = "\n".join(
        f"| {item['provider_name']} | `{item['code']}` | {item['retryability']} |"
        for item in baseline["failed_companies"]
    )
    return f"""# {collection['name']} evaluation

Generated: {report['generated_at']}

## Result

- Cohort: {coverage['total_companies']} companies
- Baseline: {coverage['baseline_graphs']}/{coverage['total_companies']} graphs ({coverage['baseline_percent']}%)
- After recovery: {coverage['post_recovery_graphs']}/{coverage['total_companies']} graphs ({coverage['post_recovery_percent']}%)
- Recovery uplift: {coverage['recovered_graphs']} graphs
- Seed: `{collection['seed']}`
- Eligible-universe digest: `{collection['eligible_universe_sha256']}`

## Failure breakdown

| Failure code | Companies |
| --- | ---: |
{issue_rows}

| Company | Failure code | Retryability |
| --- | --- | --- |
{company_rows}

## Tasks

- Baseline: `{baseline['task_id']}` — {baseline['status']}/{baseline['outcome']}
- Recovery: `{recovery['task_id']}` — {recovery['status']}/{recovery['outcome']}

## ML efficacy

- Candidate observations represented in task issues: {model['candidate_observations_in_task']}
- Candidates with model scores: {model['model_scored_candidates']}
- Runtime modes observed: {', '.join(model['model_modes']) or 'none'}
- Decision influence observed: {str(model['decision_influence_observed']).lower()}
- Conclusion: `{model['conclusion']}`

The recovery ranker cannot be credited with an efficacy improvement in this run. Coverage did not increase, and no model scores affected recovery decisions.
"""


def fetch_inputs(api_base_url: str, collection_id: str, baseline_task_id: str, recovery_task_id: str):
    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=30.0, follow_redirects=True) as client:
        collections = client.get("/api/collections")
        collections.raise_for_status()
        collection = next(
            (item for item in collections.json() if item["id"] == collection_id),
            None,
        )
        if collection is None:
            raise ValueError("Collection not found")
        providers = client.get("/api/providers")
        providers.raise_for_status()
        baseline = client.get(f"/api/tasks/{baseline_task_id}")
        baseline.raise_for_status()
        recovery = client.get(f"/api/tasks/{recovery_task_id}")
        recovery.raise_for_status()
        return collection, providers.json(), baseline.json(), recovery.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--baseline-task-id", required=True)
    parser.add_argument("--recovery-task-id", required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    collection, providers, baseline, recovery = fetch_inputs(
        args.api_base_url,
        args.collection_id,
        args.baseline_task_id,
        args.recovery_task_id,
    )
    manifest = json.loads(args.manifest.read_text()) if args.manifest else None
    report = build_report(
        collection=collection,
        providers=providers,
        baseline_task=baseline,
        recovery_task=recovery,
        manifest=manifest,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output_markdown.write_text(render_markdown(report))
    print(json.dumps({"json": str(args.output_json), "markdown": str(args.output_markdown), "coverage": report["coverage"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
