"""Run one collection-analysis provider in an isolated worker subprocess."""

from __future__ import annotations

import logging
import sys
import uuid

from poligrapher_app.services.task_execution import analyze_collection_provider
from poligrapher_app.services.tasks import TaskRegistry

logger = logging.getLogger(__name__)


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
    try:
        result = analyze_collection_provider(provider_id, task_id, TaskRegistry())
    except Exception:  # noqa: BLE001
        logger.exception("Collection subtask failed for provider %s", provider_id)
        return 1

    if result in ("ok", "unchanged"):
        return 0
    if result == "cancelled":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
