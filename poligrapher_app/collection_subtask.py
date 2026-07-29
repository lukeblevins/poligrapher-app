"""Run one collection-analysis provider in an isolated worker subprocess."""

from __future__ import annotations

import logging
import sys
import uuid
import warnings

from poligrapher_app.services.task_execution import analyze_collection_provider
from poligrapher_app.services.failures import classify_failure
from poligrapher_app.services.tasks import TaskRegistry

logger = logging.getLogger(__name__)


def _record_model_warnings(registry: TaskRegistry, task_id: str, caught) -> None:
    messages = "\n".join(str(item.message) for item in caught)
    if any(
        marker in messages
        for marker in ("[W095]", "[W113]", "strict=True", "retrain your custom model")
    ):
        issue = classify_failure(f"Model incompatible with runtime: {messages}")
        issue["severity"] = "warning"
        registry.record_issue(task_id, issue)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if len(sys.argv) != 3:
        print(
            "Usage: python -m poligrapher_app.collection_subtask PROVIDER_ID TASK_ID",
            file=sys.stderr,
        )
        return 64

    provider_id = uuid.UUID(sys.argv[1])
    task_id = sys.argv[2]
    registry = TaskRegistry()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = analyze_collection_provider(provider_id, task_id, registry)
        except Exception as exc:  # noqa: BLE001
            _record_model_warnings(registry, task_id, caught)
            registry.record_issue(
                task_id,
                classify_failure(exc),
                provider_id=provider_id,
            )
            logger.exception("Collection subtask failed for provider %s", provider_id)
            return 1
    _record_model_warnings(registry, task_id, caught)

    if result in ("ok", "unchanged"):
        return 0
    if result == "cancelled":
        return 3
    registry.record_issue(
        task_id,
        classify_failure("Run did not complete: needs_source"),
        provider_id=provider_id,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
