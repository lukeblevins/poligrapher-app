"""Consume exactly one Azure Queue task for an event-driven Container Apps Job."""

from __future__ import annotations

import _thread
import json
import logging
import os
import threading
import time

from azure.storage.queue import QueueClient

from poligrapher_app.services.task_execution import execute_task
from poligrapher_app.services.tasks import TaskRegistry

logger = logging.getLogger(__name__)


def _renew_message_lease(queue, message, stop: threading.Event, state: dict) -> None:
    visibility_timeout = int(os.getenv("AZURE_QUEUE_VISIBILITY_TIMEOUT_SECONDS", "900"))
    renewal_interval = max(30, visibility_timeout // 3)
    while not stop.wait(renewal_interval):
        for attempt in range(3):
            try:
                receipt = queue.update_message(
                    message.id,
                    state["pop_receipt"],
                    visibility_timeout=visibility_timeout,
                )
                state["pop_receipt"] = receipt.pop_receipt
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    state["error"] = exc
                    logger.exception("Queue lease renewal failed; stopping worker")
                    _thread.interrupt_main()
                    return
                time.sleep(2 ** attempt)


def main() -> None:
    connection = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    queue_name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "analysis-tasks")
    queue = QueueClient.from_connection_string(connection, queue_name)
    visibility_timeout = int(os.getenv("AZURE_QUEUE_VISIBILITY_TIMEOUT_SECONDS", "900"))
    messages = queue.receive_messages(
        messages_per_page=1,
        visibility_timeout=visibility_timeout,
    )
    message = next(iter(messages), None)
    if message is None:
        print("No queued task found.")
        return
    body = json.loads(message.content)
    lease_state = {"pop_receipt": message.pop_receipt}
    stop_renewal = threading.Event()
    renewal = threading.Thread(
        target=_renew_message_lease,
        args=(queue, message, stop_renewal, lease_state),
        daemon=True,
    )
    renewal.start()
    try:
        claimed = execute_task(body["task_id"], TaskRegistry())
    finally:
        stop_renewal.set()
        renewal.join(timeout=5)
    # A duplicate delivery that is still inside the recovery grace remains on
    # the queue. A claimed task is deleted only after its dispatcher settles.
    if claimed:
        queue.delete_message(message.id, lease_state["pop_receipt"])


if __name__ == "__main__":
    main()
