"""Reproducible, manually gated training for the cohort-recovery ranker."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import time
from typing import Iterable

from poligrapher_app.services.recovery_ranking import (
    FEATURE_SCHEMA_VERSION,
    derive_implicit_label,
)

MIN_LABELABLE_ATTEMPTS = 500
MIN_CLASS_EXAMPLES = 100
MIN_DISTINCT_PROVIDERS = 200
RANDOM_SEED = 20260817
ASSIST_MIN_SHADOW_DAYS = 30
ASSIST_MIN_LABELS = 100
ASSIST_MIN_PROVIDERS = 50
ASSIST_MIN_AP_IMPROVEMENT = 0.05
ASSIST_MAX_P95_INFERENCE_MS = 50.0


def build_recovery_dataset(session) -> list[dict]:
    """Return feature-only labeled observations; URLs and policy text are omitted."""

    from poligrapher_app.api.models import RecoveryCandidateObservation

    rows: list[dict] = []
    observations = (
        session.query(RecoveryCandidateObservation)
        .filter(RecoveryCandidateObservation.outcome_code.isnot(None))
        .order_by(RecoveryCandidateObservation.created_at, RecoveryCandidateObservation.id)
        .all()
    )
    for observation in observations:
        label = derive_implicit_label(observation.outcome_code)
        if label is None:
            continue
        features = dict(observation.features or {})
        if features.get("feature_schema") != FEATURE_SCHEMA_VERSION:
            continue
        rows.append({
            "observation_id": str(observation.id),
            "provider_id": str(observation.provider_id),
            "created_at": observation.created_at,
            "features": features,
            "heuristic_confidence": float(observation.heuristic_confidence),
            "label": label,
        })
    return rows


def validate_training_population(rows: list[dict]) -> None:
    labels = Counter(row["label"] for row in rows)
    providers = {row["provider_id"] for row in rows}
    errors = []
    if len(rows) < MIN_LABELABLE_ATTEMPTS:
        errors.append(f"{len(rows)} labelable attempts; need {MIN_LABELABLE_ATTEMPTS}")
    for label, name in ((1, "positive"), (0, "negative")):
        if labels[label] < MIN_CLASS_EXAMPLES:
            errors.append(f"{labels[label]} {name} outcomes; need {MIN_CLASS_EXAMPLES}")
    if len(providers) < MIN_DISTINCT_PROVIDERS:
        errors.append(f"{len(providers)} providers; need {MIN_DISTINCT_PROVIDERS}")
    if errors:
        raise ValueError("Training population is not ready: " + "; ".join(errors))


def split_by_provider_and_time(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Use ordered provider groups so no company leaks across partitions."""

    first_seen: dict[str, datetime] = {}
    for row in rows:
        created_at = row["created_at"]
        first_seen[row["provider_id"]] = min(first_seen.get(row["provider_id"], created_at), created_at)
    providers = sorted(first_seen, key=lambda provider_id: (first_seen[provider_id], provider_id))
    train_end = max(1, int(len(providers) * 0.6))
    validation_end = max(train_end + 1, int(len(providers) * 0.8))
    train_ids = set(providers[:train_end])
    validation_ids = set(providers[train_end:validation_end])
    test_ids = set(providers[validation_end:])
    partitions = tuple(
        [row for row in rows if row["provider_id"] in ids]
        for ids in (train_ids, validation_ids, test_ids)
    )
    for name, partition in zip(("train", "validation", "test"), partitions, strict=True):
        if {row["label"] for row in partition} != {0, 1}:
            raise ValueError(f"{name} split must contain both outcome classes")
    return partitions


def _xy(rows: Iterable[dict]) -> tuple[list[dict], list[int]]:
    values = list(rows)
    return [row["features"] for row in values], [row["label"] for row in values]


def _metrics(model, rows: list[dict]) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss

    x, y = _xy(rows)
    probabilities = model.predict_proba(x)[:, 1]
    return {
        "average_precision": float(average_precision_score(y, probabilities)),
        "brier_score": float(brier_score_loss(y, probabilities)),
    }


def _heuristic_metrics(rows: list[dict]) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss

    labels = [row["label"] for row in rows]
    scores = [row["heuristic_confidence"] for row in rows]
    return {
        "average_precision": float(average_precision_score(labels, scores)),
        "brier_score": float(brier_score_loss(labels, scores)),
    }


def evaluate_against_heuristic(model, rows: list[dict]) -> dict:
    model_metrics = _metrics(model, rows)
    heuristic_metrics = _heuristic_metrics(rows)
    return {
        "model": model_metrics,
        "heuristic": heuristic_metrics,
        "average_precision_improvement": (
            model_metrics["average_precision"] - heuristic_metrics["average_precision"]
        ),
    }


def _bootstrap_ap_improvement(model, rows: list[dict], samples: int = 1000) -> tuple[float, float]:
    from sklearn.metrics import average_precision_score

    rng = random.Random(RANDOM_SEED)
    x, labels = _xy(rows)
    model_scores = list(model.predict_proba(x)[:, 1])
    heuristic_scores = [row["heuristic_confidence"] for row in rows]
    improvements: list[float] = []
    for _ in range(samples):
        indexes = [rng.randrange(len(rows)) for _ in rows]
        sampled_labels = [labels[index] for index in indexes]
        if len(set(sampled_labels)) < 2:
            continue
        model_ap = average_precision_score(sampled_labels, [model_scores[index] for index in indexes])
        heuristic_ap = average_precision_score(sampled_labels, [heuristic_scores[index] for index in indexes])
        improvements.append(float(model_ap - heuristic_ap))
    if not improvements:
        return 0.0, 0.0
    improvements.sort()
    return (
        improvements[int(len(improvements) * 0.025)],
        improvements[min(len(improvements) - 1, int(len(improvements) * 0.975))],
    )


def _p95_inference_ms(model, rows: list[dict]) -> float:
    timings = []
    for row in rows[: min(200, len(rows))]:
        started = time.perf_counter()
        model.predict_proba([row["features"]])
        timings.append((time.perf_counter() - started) * 1000)
    timings.sort()
    return timings[min(len(timings) - 1, int(len(timings) * 0.95))] if timings else 0.0


def build_shadow_summary(session, model_version: str) -> dict:
    """Summarize labeled shadow use for a specific checksum-pinned model."""

    from poligrapher_app.api.models import RecoveryCandidateObservation

    observations = (
        session.query(RecoveryCandidateObservation)
        .filter_by(model_mode="shadow", model_version=model_version)
        .order_by(RecoveryCandidateObservation.created_at)
        .all()
    )
    labeled = [
        item
        for item in observations
        if derive_implicit_label(item.outcome_code) is not None
    ]
    dates = [item.settled_at or item.created_at for item in labeled]
    return {
        "model_version": model_version,
        "labelable_attempts": len(labeled),
        "providers": len({item.provider_id for item in labeled}),
        "shadow_days": (
            (max(dates) - min(dates)).total_seconds() / 86400
            if len(dates) >= 2
            else 0.0
        ),
        "safety_rule_bypasses": sum(
            item.decision == "attempt" and item.hard_rule_status != "eligible"
            for item in observations
        ),
    }


def assess_assist_readiness(report: dict, shadow_summary: dict) -> dict:
    """Apply every promotion gate; callers cannot silently skip a criterion."""

    checks = {
        "shadow_duration": shadow_summary.get("shadow_days", 0) >= ASSIST_MIN_SHADOW_DAYS,
        "shadow_labels": shadow_summary.get("labelable_attempts", 0) >= ASSIST_MIN_LABELS,
        "shadow_providers": shadow_summary.get("providers", 0) >= ASSIST_MIN_PROVIDERS,
        "average_precision_gain": (
            report.get("average_precision_improvement", 0)
            >= ASSIST_MIN_AP_IMPROVEMENT
        ),
        "brier_non_worse": (
            report.get("test", {}).get("brier_score", 1)
            <= report.get("heuristic_test", {}).get("brier_score", 0)
        ),
        "bootstrap_lower_bound_positive": (
            (report.get("bootstrap_ap_improvement_95ci") or [0])[0] > 0
        ),
        "safety_rules_intact": shadow_summary.get("safety_rule_bypasses", 1) == 0,
        "inference_latency": (
            report.get("p95_inference_ms", float("inf"))
            < ASSIST_MAX_P95_INFERENCE_MS
        ),
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def train_candidate_models(rows: list[dict]):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    validate_training_population(rows)
    train_rows, validation_rows, test_rows = split_by_provider_and_time(rows)
    train_x, train_y = _xy(train_rows)
    models = {
        "logistic_regression": Pipeline([
            ("features", DictVectorizer(sparse=False)),
            ("classifier", LogisticRegression(
                class_weight="balanced",
                max_iter=2000,
                random_state=RANDOM_SEED,
            )),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("features", DictVectorizer(sparse=False)),
            ("classifier", HistGradientBoostingClassifier(
                class_weight="balanced",
                learning_rate=0.05,
                max_iter=200,
                max_leaf_nodes=15,
                random_state=RANDOM_SEED,
            )),
        ]),
    }
    validation_metrics = {}
    for name, model in models.items():
        model.fit(train_x, train_y)
        validation_metrics[name] = _metrics(model, validation_rows)
    logistic_ap = validation_metrics["logistic_regression"]["average_precision"]
    boosted_ap = validation_metrics["hist_gradient_boosting"]["average_precision"]
    selected_name = (
        "hist_gradient_boosting"
        if boosted_ap >= logistic_ap + 0.02
        else "logistic_regression"
    )
    selected = models[selected_name]
    combined_x, combined_y = _xy(train_rows + validation_rows)
    selected.fit(combined_x, combined_y)
    test_metrics = _metrics(selected, test_rows)
    heuristic_metrics = _heuristic_metrics(test_rows)
    confidence_interval = _bootstrap_ap_improvement(selected, test_rows)
    report = {
        "selected_model": selected_name,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "population": {
            "observations": len(rows),
            "providers": len({row["provider_id"] for row in rows}),
            "positive": sum(row["label"] == 1 for row in rows),
            "negative": sum(row["label"] == 0 for row in rows),
            "train": len(train_rows),
            "validation": len(validation_rows),
            "test": len(test_rows),
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "heuristic_test": heuristic_metrics,
        "average_precision_improvement": (
            test_metrics["average_precision"]
            - heuristic_metrics["average_precision"]
        ),
        "bootstrap_ap_improvement_95ci": list(confidence_interval),
        "p95_inference_ms": _p95_inference_ms(selected, test_rows),
    }
    return selected, report


def dataset_digest(rows: list[dict]) -> str:
    canonical = [
        {
            **row,
            "created_at": row["created_at"].isoformat(),
        }
        for row in sorted(rows, key=lambda item: item["observation_id"])
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def write_model_bundle(model, report: dict, rows: list[dict], output_dir: Path) -> dict:
    import sklearn
    import skops
    import skops.io as sio

    output_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = output_dir / f"recovery-ranker-{version}.skops"
    sio.dump(model, artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "version": version,
        "sha256": digest,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_sha256": dataset_digest(rows),
        "python_version": platform.python_version(),
        "scikit_learn_version": sklearn.__version__,
        "skops_version": skops.__version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = artifact.with_name(f"{artifact.stem}.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / f"{artifact.stem}.metrics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / f"{artifact.stem}.model-card.md").write_text(
        "# Cohort recovery ranker\n\n"
        f"- Version: `{version}`\n"
        f"- Dataset digest: `{manifest['dataset_sha256']}`\n"
        f"- Selected model: `{report['selected_model']}`\n"
        "- Intended use: shadow scoring and review-only candidate ranking.\n"
        "- Not intended to override source provenance, scope, or validation rules.\n"
        "- Labels represent operational recoverability and may not detect a semantically narrow policy.\n",
        encoding="utf-8",
    )
    return {"artifact": str(artifact), "manifest": manifest, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the recovery candidate ranker")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    from poligrapher_app.api.database import SessionLocal

    with SessionLocal() as session:
        rows = build_recovery_dataset(session)
    model, report = train_candidate_models(rows)
    bundle = write_model_bundle(model, report, rows, args.output_dir)
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
