import pytest

from poligrapher_app.experiments.report_catalog_cohort import build_report, render_markdown


def _task(task_id, *, total=2, failed=1, issues=()):
    return {
        "task_id": task_id,
        "status": "done",
        "outcome": "partially_succeeded" if failed else "succeeded",
        "total": total,
        "completed": total,
        "failed": failed,
        "issues": list(issues),
    }


def _issue(name, code, *, retryability="manual", details=None):
    return {
        "provider_id": name.casefold(),
        "provider_name": name,
        "code": code,
        "retryability": retryability,
        "actions": [{"action": "replace_source", "label": "Replace source"}],
        "details": details or {},
    }


def test_report_measures_coverage_and_does_not_credit_heuristic_fallback():
    collection = {
        "id": "collection-1",
        "name": "Pilot",
        "description": "seed=7; eligible_universe_sha256=" + "a" * 64 + "; manifest_schema=1.",
        "provider_ids": ["alpha", "bravo"],
        "provider_count": 2,
    }
    providers = [
        {"id": "alpha", "name": "Alpha", "analyzed_count": 1},
        {"id": "bravo", "name": "Bravo", "analyzed_count": 0},
    ]
    baseline = _task("baseline", issues=[_issue("Bravo", "source.not_policy")])
    recovery = _task(
        "recovery",
        issues=[_issue("Bravo", "recovery.review_required", details={"candidates": [{
            "model_mode": "shadow",
            "model_score": None,
        }]})],
    )

    report = build_report(
        collection=collection,
        providers=providers,
        baseline_task=baseline,
        recovery_task=recovery,
        generated_at="2026-08-26T00:00:00+00:00",
    )

    assert report["coverage"] == {
        "baseline_graphs": 1,
        "post_recovery_graphs": 1,
        "total_companies": 2,
        "baseline_percent": 50.0,
        "post_recovery_percent": 50.0,
        "recovered_graphs": 0,
        "unresolved_companies": ["Bravo"],
    }
    assert report["baseline"]["issues_by_code"] == {"source.not_policy": 1}
    assert report["model_efficacy"]["conclusion"] == "not_evaluated_no_model_scores"
    assert report["model_efficacy"]["decision_influence_observed"] is False
    assert report["collection"]["seed"] == 7


def test_report_reads_candidates_from_technical_detail_and_renders_markdown():
    collection = {
        "id": "collection-1",
        "name": "Pilot",
        "description": None,
        "provider_ids": ["alpha"],
        "provider_count": 1,
    }
    providers = [{"id": "alpha", "name": "Alpha", "analyzed_count": 1}]
    baseline = _task("baseline", total=1, failed=0)
    recovery_issue = _issue("Alpha", "recovery.review_required")
    recovery_issue["technical_detail"] = '{"candidates":[{"model_mode":"shadow","model_score":0.8}]}'
    recovery = _task("recovery", total=1, failed=0, issues=[recovery_issue])

    report = build_report(
        collection=collection,
        providers=providers,
        baseline_task=baseline,
        recovery_task=recovery,
        manifest={
            "seed": 9,
            "schema_version": 1,
            "snapshots": {"eligible_universe_sha256": "b" * 64},
        },
    )
    markdown = render_markdown(report)

    assert report["model_efficacy"]["model_scored_candidates"] == 1
    assert report["model_efficacy"]["conclusion"] == "shadow_scores_could_not_affect_decisions"
    assert "Recovery uplift: 0 graphs" in markdown
    assert "`shadow_scores_could_not_affect_decisions`" in markdown


def test_report_refuses_an_incomplete_provider_snapshot():
    collection = {
        "id": "collection-1",
        "name": "Pilot",
        "description": None,
        "provider_ids": ["alpha", "bravo"],
        "provider_count": 2,
    }

    with pytest.raises(ValueError, match="Provider snapshot does not contain the complete collection"):
        build_report(
            collection=collection,
            providers=[{"id": "alpha", "name": "Alpha", "analyzed_count": 1}],
            baseline_task=_task("baseline"),
            recovery_task=_task("recovery"),
        )


def test_report_refuses_a_nonterminal_task():
    collection = {
        "id": "collection-1",
        "name": "Pilot",
        "description": None,
        "provider_ids": ["alpha"],
        "provider_count": 1,
    }
    baseline = _task("baseline", total=1, failed=0)
    baseline["status"] = "running"

    with pytest.raises(ValueError, match="Evaluation tasks must be terminal before reporting"):
        build_report(
            collection=collection,
            providers=[{"id": "alpha", "name": "Alpha", "analyzed_count": 1}],
            baseline_task=baseline,
            recovery_task=_task("recovery", total=1, failed=0),
        )
