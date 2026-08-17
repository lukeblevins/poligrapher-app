"""Feature extraction, shadow scoring, and implicit labels for source recovery."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import urllib.parse

logger = logging.getLogger(__name__)

FEATURE_SCHEMA_VERSION = "recovery-candidate-v1"
VALID_MODES = frozenset({"off", "shadow", "assist"})
CANDIDATE_FEATURE_KEYS = frozenset({
    "access_restricted",
    "is_pdf",
    "link_score",
    "same_registrable_domain",
    "search_score",
})
POSITIVE_OUTCOMES = frozenset({"retained_graph_success"})
NEGATIVE_OUTCOMES = frozenset({
    "acquisition_failed",
    "validation_failed",
    "extraction_failed",
    "graph_failed",
    "graph_empty",
    "rolled_back_source_failure",
})


@dataclass(frozen=True)
class RankerState:
    mode: str
    version: str | None = None
    available: bool = False
    error: str | None = None


def recovery_ranker_mode() -> str:
    mode = (os.getenv("RECOVERY_RANKER_MODE") or "shadow").strip().casefold()
    if mode not in VALID_MODES:
        logger.warning("Unknown RECOVERY_RANKER_MODE=%r; using off", mode)
        return "off"
    return mode


def extract_candidate_features(target, candidate) -> dict[str, str | float | int | bool]:
    """Build a stable pre-decision feature vector without policy text."""

    from poligrapher_app.services.acquisition import narrow_policy_reason, registrable_domain

    parsed = urllib.parse.urlparse(candidate.url)
    expected_host = (target.domain or "").casefold().strip(". ").removeprefix("www.")
    host = (parsed.hostname or "").casefold().strip(".")
    path = parsed.path.casefold()
    note_score = re.search(r"score\s+(\d+)", candidate.notes or "", re.I)
    features: dict[str, str | float | int | bool] = {
        "feature_schema": FEATURE_SCHEMA_VERSION,
        "strategy": candidate.strategy,
        "root_code": target.root_code,
        "root_retryability": target.root_retryability,
        "heuristic_confidence": float(candidate.confidence),
        "validated": bool(getattr(candidate, "validated", False)),
        "canonical_host": bool(expected_host and host in {expected_host, f"www.{expected_host}"}),
        "same_registrable_domain": bool(
            target.domain and registrable_domain(candidate.url) == registrable_domain(target.domain)
        ),
        "is_pdf": path.endswith(".pdf"),
        "privacy_in_path": "privacy" in path or "data-protection" in path,
        "secure_scheme": parsed.scheme == "https",
        "path_depth": len([part for part in parsed.path.split("/") if part]),
        "audience_or_document_reason": narrow_policy_reason(f"{candidate.url} {candidate.notes}") or "none",
        "source_revalidated": bool(target.source_revalidated),
    }
    if note_score:
        features["resolver_score"] = int(note_score.group(1))
    for key, value in (getattr(candidate, "features", {}) or {}).items():
        if key in CANDIDATE_FEATURE_KEYS and isinstance(value, (str, float, int, bool)):
            features[key] = value
    return features


def hard_rule_decision(target, candidate, *, selected_status: str | None = None) -> tuple[str, list[str]]:
    """Describe deterministic eligibility; the model never changes this result."""

    from poligrapher_app.services.acquisition import AUTO_CONFIDENCE, narrow_policy_reason

    reasons: list[str] = []
    narrow = narrow_policy_reason(f"{candidate.url} {candidate.notes}")
    if narrow:
        reasons.append(narrow)
    if not getattr(candidate, "validated", False):
        reasons.append("source.unvalidated")
    if candidate.confidence < AUTO_CONFIDENCE:
        reasons.append("confidence.below_auto_threshold")
    if selected_status == "replacement_found" and not reasons:
        return "eligible", []
    if selected_status == "review_required" or reasons:
        return "review", reasons
    return "unselected", reasons


apply_recovery_safety_rules = hard_rule_decision


class RecoveryCandidateRanker:
    """Lazy checksum-verified model loader with an exact heuristic fallback."""

    def __init__(self) -> None:
        self.mode = recovery_ranker_mode()
        self.model = None
        self.version: str | None = None
        self.error: str | None = None
        if self.mode != "off":
            self._load()

    @property
    def state(self) -> RankerState:
        return RankerState(self.mode, self.version, self.model is not None, self.error)

    def _load(self) -> None:
        configured = (os.getenv("RECOVERY_RANKER_PATH") or "").strip()
        if not configured:
            pointer = Path(__file__).resolve().parents[1] / "model_artifacts" / "recovery_ranker" / "active.json"
            if not pointer.is_file():
                self.error = "No recovery ranker artifact is configured"
                return
            try:
                configured = str(pointer.parent / json.loads(pointer.read_text(encoding="utf-8"))["artifact"])
            except Exception as exc:  # noqa: BLE001
                self.error = f"Recovery ranker pointer is invalid: {exc}"
                return
        artifact = Path(configured).resolve()
        manifest_path = artifact.with_name(f"{artifact.stem}.manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if digest != manifest["sha256"]:
                raise ValueError("Recovery ranker checksum does not match its manifest")
            if manifest.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
                raise ValueError("Recovery ranker feature schema is incompatible")
            import skops.io as sio

            unknown = sio.get_untrusted_types(file=artifact)
            disallowed = [name for name in unknown if not name.startswith(("sklearn.", "numpy."))]
            if disallowed:
                raise ValueError(f"Recovery ranker contains unsupported types: {', '.join(disallowed)}")
            self.model = sio.load(artifact, trusted=unknown)
            self.version = str(manifest["version"])
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            logger.warning("Recovery ranker unavailable; using heuristic fallback: %s", exc)

    def score(self, features: dict) -> float | None:
        if self.model is None:
            return None
        probability = self.model.predict_proba([features])[0][1]
        return float(max(0.0, min(1.0, probability)))


def score_recovery_candidates(
    target,
    candidates,
    *,
    selected_url: str | None,
    selected_status: str | None,
    ranker: RecoveryCandidateRanker | None = None,
) -> tuple[list[dict], RecoveryCandidateRanker]:
    """Score bounded evidence while preserving its original resolver order."""

    ranker = ranker or RecoveryCandidateRanker()
    evidence = []
    for candidate in list(candidates)[:10]:
        selected = bool(selected_url and candidate.url.rstrip("/") == selected_url.rstrip("/"))
        features = extract_candidate_features(target, candidate)
        hard_status, hard_reasons = hard_rule_decision(
            target,
            candidate,
            selected_status=selected_status if selected else None,
        )
        evidence.append({
            "url": candidate.url,
            "strategy": candidate.strategy,
            "heuristic_confidence": candidate.confidence,
            "validated": bool(getattr(candidate, "validated", False)),
            "features": features,
            "hard_rule_status": hard_status,
            "hard_rule_reasons": hard_reasons,
            "model_mode": ranker.state.mode,
            "model_version": ranker.state.version,
            "model_score": ranker.score(features),
            "selected": selected,
        })
    return evidence, ranker


def derive_implicit_label(outcome_code: str | None) -> int | None:
    if outcome_code in POSITIVE_OUTCOMES:
        return 1
    if outcome_code in NEGATIVE_OUTCOMES:
        return 0
    return None
