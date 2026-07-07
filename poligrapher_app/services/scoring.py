"""Policy scoring services.

Wraps the in-repo :class:`PrivacyScorer` and the external ``policy-scorer``
package (GDPR scheme). Both operate on a :class:`PolicyDocumentInfo` and mutate
its ``latest_*_result`` / ``score`` fields, but hold no HTTP/view knowledge.
"""

import logging

from poligrapher_app.domain.policy_analysis import PolicyDocumentInfo
from poligrapher_app.scoring import PrivacyScorer

logger = logging.getLogger(__name__)

# The GDPR scheme is loaded once and cached; PolicyScorer is stateless per call.
_gdpr_scorer = None


def _get_gdpr_scorer():
    global _gdpr_scorer
    if _gdpr_scorer is None:
        from policy_scorer import PolicyScorer, get_scheme

        _gdpr_scorer = PolicyScorer(get_scheme("gdpr"))
    return _gdpr_scorer


def score_privacy(policy: PolicyDocumentInfo) -> float | None:
    """Score a policy with the in-repo heuristic PrivacyScorer."""
    policy.has_results = False
    if not policy.has_graph():
        logger.error("No graph found to score document at %s", policy.output_dir)
        return None

    scorer = PrivacyScorer()
    results = scorer.score_policy(policy.get_document_text())
    policy.set_privacy_result(results)
    if results.get("success"):
        policy.has_results = True
    else:
        policy.score = None
    return policy.score


def score_gdpr(policy: PolicyDocumentInfo) -> float | None:
    """Score a policy against the GDPR scheme using the policy-scorer package."""
    policy.has_results = False
    if not policy.has_graph():
        logger.error("No graph found to score document at %s", policy.output_dir)
        return None

    artifacts = policy.load_graph_artifacts()
    scorer = _get_gdpr_scorer()
    results = scorer.score_policy(
        policy.get_document_text(),
        graphml_graph=artifacts.get("graphml_graph"),
        yaml_graph=artifacts.get("yaml_graph"),
    )
    policy.set_gdpr_result(results)
    if results.get("success"):
        policy.has_results = True
    else:
        policy.score = None
    return policy.score
