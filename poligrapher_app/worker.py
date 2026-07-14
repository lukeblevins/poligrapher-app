"""Consume exactly one Azure Queue task for an event-driven Container Apps Job."""

from __future__ import annotations

import json
import os

from azure.storage.queue import QueueClient

from poligrapher_app.services.task_execution import execute_task
from poligrapher_app.services.tasks import TaskRegistry


def main() -> None:
    connection = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    queue_name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "analysis-tasks")
    queue = QueueClient.from_connection_string(connection, queue_name)
    messages = queue.receive_messages(messages_per_page=1, visibility_timeout=7200)
    message = next(iter(messages), None)
    if message is None:
        print("No queued task found.")
        return
    body = json.loads(message.content)
    execute_task(body["task_id"], TaskRegistry())
    # Delete only after the dispatcher returns. Infrastructure exceptions leave
    # the message for recovery after its visibility lease expires.
    queue.delete_message(message)


if __name__ == "__main__":
    main()
