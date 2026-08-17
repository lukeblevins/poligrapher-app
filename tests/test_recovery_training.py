from datetime import datetime, timedelta, timezone

import pytest

from poligrapher_app.ml import recovery_training
from poligrapher_app.services.recovery_ranking import FEATURE_SCHEMA_VERSION, RecoveryCandidateRanker


def _rows(count: int = 500) -> list[dict]:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        label = index % 2
        rows.append({
            "observation_id": f"observation-{index:04d}",
            "provider_id": f"provider-{index // 2:04d}",
            "created_at": started + timedelta(hours=index),
            "features": {
                "feature_schema": FEATURE_SCHEMA_VERSION,
                "strategy": "search" if label else "discovery",
                "validated": bool(label),
                "canonical_host": bool(label),
                "heuristic_confidence": 0.7 + label * 0.1,
            },
            "heuristic_confidence": 0.7 + label * 0.1,
            "label": label,
        })
    return rows


def test_training_refuses_an_undersized_population():
    with pytest.raises(ValueError, match="Training population is not ready"):
        recovery_training.validate_training_population(_rows(20))


def test_split_keeps_every_provider_in_one_partition():
    train, validation, test = recovery_training.split_by_provider_and_time(_rows())
    provider_sets = [{row["provider_id"] for row in partition} for partition in (train, validation, test)]
    assert provider_sets[0].isdisjoint(provider_sets[1])
    assert provider_sets[0].isdisjoint(provider_sets[2])
    assert provider_sets[1].isdisjoint(provider_sets[2])
    assert sum(map(len, (train, validation, test))) == 500


def test_training_selects_a_model_and_reports_against_the_heuristic():
    model, report = recovery_training.train_candidate_models(_rows())
    assert report["selected_model"] in {"logistic_regression", "hist_gradient_boosting"}
    assert report["population"]["observations"] == 500
    assert "average_precision" in report["test"]
    assert model.predict_proba([_rows(1)[0]["features"]]).shape == (1, 2)


def test_model_bundle_round_trip_is_checksum_verified(tmp_path, monkeypatch):
    rows = _rows()
    model, report = recovery_training.train_candidate_models(rows)
    bundle = recovery_training.write_model_bundle(model, report, rows, tmp_path)
    monkeypatch.setenv("RECOVERY_RANKER_MODE", "shadow")
    monkeypatch.setenv("RECOVERY_RANKER_PATH", bundle["artifact"])

    ranker = RecoveryCandidateRanker()
    assert ranker.state.available is True
    assert ranker.state.version == bundle["manifest"]["version"]
    assert ranker.score(rows[0]["features"]) is not None

    artifact = tmp_path / bundle["artifact"]
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    broken = RecoveryCandidateRanker()
    assert broken.state.available is False
    assert "checksum" in (broken.state.error or "").casefold()


def test_assist_readiness_requires_every_promotion_gate():
    report = {
        "average_precision_improvement": 0.06,
        "test": {"brier_score": 0.15},
        "heuristic_test": {"brier_score": 0.2},
        "bootstrap_ap_improvement_95ci": [0.01, 0.1],
        "p95_inference_ms": 2.0,
    }
    shadow = {
        "shadow_days": 31,
        "labelable_attempts": 101,
        "providers": 51,
        "safety_rule_bypasses": 0,
    }

    assert recovery_training.assess_assist_readiness(report, shadow)["eligible"] is True
    shadow["safety_rule_bypasses"] = 1
    assessment = recovery_training.assess_assist_readiness(report, shadow)
    assert assessment["eligible"] is False
    assert assessment["failed_checks"] == ["safety_rules_intact"]
