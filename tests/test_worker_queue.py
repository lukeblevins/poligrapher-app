from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from poligrapher_app import worker


@pytest.mark.parametrize(
    'claimed,status,deleted',
    [(True, 'done', True), (False, 'done', True), (False, 'failed', True),
     (False, 'cancelled', True), (False, 'running', False),
     (False, 'queued', False), (False, None, False)],
)
def test_worker_acknowledges_settled_tasks_but_preserves_live_duplicates(
    monkeypatch, claimed, status, deleted,
):
    message = SimpleNamespace(id='message', pop_receipt='receipt',
                              content='{"task_id": "task"}')
    queue = Mock()
    queue.receive_messages.return_value = iter([message])
    registry = Mock()
    registry.get.return_value = {'status': status} if status else None
    monkeypatch.setenv('AZURE_STORAGE_CONNECTION_STRING', 'test')
    monkeypatch.setattr(worker.QueueClient, 'from_connection_string', Mock(return_value=queue))
    monkeypatch.setattr(worker, 'TaskRegistry', Mock(return_value=registry))
    monkeypatch.setattr(worker, 'execute_task', Mock(return_value=claimed))
    worker.main()
    assert queue.delete_message.called is deleted
    if deleted:
        queue.delete_message.assert_called_once_with('message', 'receipt')


def test_worker_preserves_message_when_dispatch_crashes(monkeypatch):
    queue = Mock()
    queue.receive_messages.return_value = iter([
        SimpleNamespace(id='message', pop_receipt='receipt', content='{"task_id":"task"}'),
    ])
    monkeypatch.setenv('AZURE_STORAGE_CONNECTION_STRING', 'test')
    monkeypatch.setattr(worker.QueueClient, 'from_connection_string', Mock(return_value=queue))
    monkeypatch.setattr(worker, 'TaskRegistry', Mock())
    monkeypatch.setattr(worker, 'execute_task', Mock(side_effect=RuntimeError('unavailable')))
    with pytest.raises(RuntimeError):
        worker.main()
    queue.delete_message.assert_not_called()
