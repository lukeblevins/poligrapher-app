import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Provider, RecoveryCandidateObservation, TaskRecord
from poligrapher_app.services.acquisition import SourceCandidate
from poligrapher_app.services.cohort_audit import AuditStatus, SourceAuditResult, SourceAuditTarget
from poligrapher_app.services.cohort_recovery import (
    _record_candidate_observations,
    _settle_candidate_observation,
)
from poligrapher_app.services.recovery_ranking import (
    FEATURE_SCHEMA_VERSION,
    RecoveryCandidateRanker,
    derive_implicit_label,
    extract_candidate_features,
    hard_rule_decision,
)


def _target() -> SourceAuditTarget:
    return SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example Company",
        domain="example.com",
        source_url="https://example.com/old",
        root_code="source.not_policy",
    )


def test_candidate_features_are_predecision_and_company_agnostic():
    target = _target()
    candidate = SourceCandidate(
        "https://www.example.com/legal/privacy-policy.pdf",
        "search",
        0.84,
        notes="validated public search result (score 15)",
        validated=True,
        features={"feature_schema": "malicious", "search_score": 22},
    )
    features = extract_candidate_features(target, candidate)

    assert features["feature_schema"] == FEATURE_SCHEMA_VERSION
    assert features["canonical_host"] is True
    assert features["is_pdf"] is True
    assert features["resolver_score"] == 15
    assert features["search_score"] == 22
    assert features["feature_schema"] == FEATURE_SCHEMA_VERSION
    assert "Example Company" not in repr(features)
    assert candidate.url not in repr(features)


def test_hard_rules_remain_authoritative_over_confidence():
    target = _target()
    candidate = SourceCandidate(
        "https://example.com/employees/privacy",
        "search",
        0.99,
        validated=True,
    )
    status, reasons = hard_rule_decision(target, candidate, selected_status="replacement_found")
    assert status == "review"
    assert "audience.workforce" in reasons


@pytest.mark.parametrize(
    ("outcome", "label"),
    [
        ("retained_graph_success", 1),
        ("validation_failed", 0),
        ("graph_failed", 0),
        ("transient_execution_failure", None),
        (None, None),
    ],
)
def test_implicit_labels_are_conservative(outcome, label):
    assert derive_implicit_label(outcome) == label


def test_missing_shadow_artifact_uses_heuristic_fallback(monkeypatch):
    monkeypatch.setenv("RECOVERY_RANKER_MODE", "shadow")
    monkeypatch.delenv("RECOVERY_RANKER_PATH", raising=False)
    ranker = RecoveryCandidateRanker()
    assert ranker.state.mode == "shadow"
    assert ranker.state.available is False
    assert ranker.score({"strategy": "search"}) is None


@pytest.mark.parametrize(
    ("mode", "expected_url"),
    [
        ("shadow", "https://review.example/first"),
        ("assist", "https://review.example/second"),
    ],
)
def test_model_only_reorders_review_candidates_in_assist(monkeypatch, mode, expected_url):
    from poligrapher_app.services import cohort_audit, recovery_ranking
    from poligrapher_app.services.recovery_ranking import RankerState

    class Ranker:
        state = RankerState(mode=mode, version="test", available=True)

        @staticmethod
        def score(features):
            return 0.9 if features["strategy"] == "linked" else 0.1

    monkeypatch.setattr(recovery_ranking, "RecoveryCandidateRanker", Ranker)
    result = SourceAuditResult(
        target=_target(),
        status=AuditStatus.REVIEW_REQUIRED,
        replacement_url="https://review.example/first",
        replacement_strategy="search",
        replacement_confidence=0.75,
    )
    resolver = type("Resolver", (), {
        "observed_candidates": [
            SourceCandidate("https://review.example/first", "search", 0.75, validated=True),
            SourceCandidate("https://review.example/second", "linked", 0.72, validated=True),
        ],
    })()

    finished = cohort_audit._finish_with_candidate_evidence(result, resolver)

    assert finished.status is AuditStatus.REVIEW_REQUIRED
    assert finished.auto_attempt_url is None
    assert finished.replacement_url == expected_url


def test_observation_is_persisted_and_settled_for_a_real_task():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(name="Example", domain="example.com")
        task = TaskRecord(kind="cohort-recovery")
        db.add_all([provider, task])
        db.commit()
        result = SourceAuditResult(
            target=SourceAuditTarget(
                provider_id=provider.id,
                provider_name=provider.name,
                domain=provider.domain,
                source_url=None,
                root_code="source.missing",
            ),
            status=AuditStatus.REPLACEMENT_FOUND,
            replacement_url="https://example.com/privacy",
            candidate_evidence=[{
                "url": "https://example.com/privacy",
                "strategy": "search",
                "heuristic_confidence": 0.84,
                "features": {"feature_schema": FEATURE_SCHEMA_VERSION},
                "hard_rule_status": "eligible",
                "hard_rule_reasons": [],
                "model_mode": "shadow",
                "model_version": None,
                "model_score": None,
                "selected": True,
            }],
        )
        _record_candidate_observations(db, str(task.id), result)
        observation = db.query(RecoveryCandidateObservation).one()
        assert observation.decision == "attempt"
        assert observation.outcome_code is None

        _settle_candidate_observation(db, str(task.id), provider.id, recovered=True)
        db.refresh(observation)
        assert observation.outcome_code == "retained_graph_success"
        assert observation.settled_at is not None
