import copy
import json
import sys
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from poligrapher_app import cost_guard as guard
from poligrapher_app.cost_worker import run_bounded

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def ledger():
    return {'version': 1, 'month': '2026-09', 'allowance': 10.0,
            'initial_spend': 0, 'paused': False, 'reservations': []}


def test_reservations_prevent_concurrent_or_excess_spending():
    state, first = guard.reserve(ledger(), NOW, 5)
    assert first['seconds'] == 43200
    assert first['charge'] == pytest.approx(6.525)
    unchanged, denied = guard.reserve(state, NOW, 5)
    assert denied is None
    assert unchanged == state
    first.update(settled=True, status='Failed')
    state, second = guard.reserve(state, NOW, 5)
    assert second['seconds'] < 43200
    assert sum(x['charge'] for x in state['reservations']) <= 10
    second.update(settled=True, status='Failed')
    state, denied = guard.reserve(state, NOW, 5)
    assert denied is None and state['paused']


@pytest.mark.parametrize('change,cost', [({'paused': True}, 5), ({'month': '2026-08'}, 5), ({}, 28)])
def test_paused_month_change_and_billing_stop_prevent_dispatch(change, cost):
    state = ledger() | change
    result, item = guard.reserve(state, NOW, cost)
    assert item is None and result['paused']


def test_month_boundary_limits_runtime():
    now = datetime(2026, 9, 30, 23, tzinfo=timezone.utc)
    _, item = guard.reserve(ledger(), now, 5)
    assert item['seconds'] == 3300


def test_success_refunds_only_proven_runtime_with_startup_margin():
    _, item = guard.reserve(ledger(), NOW, 5)
    guard.settle(item, {'properties': {'status': 'Succeeded',
        'startTime': '2026-09-12T00:00:00Z', 'endTime': '2026-09-12T01:00:00Z'}})
    assert item['settled']
    assert item['charge'] == pytest.approx(3900 * guard.RATE)


@pytest.mark.parametrize('status', ['Failed', 'Stopped'])
def test_failed_execution_keeps_full_reservation(status):
    _, item = guard.reserve(ledger(), NOW, 5)
    charge = item['charge']
    guard.settle(item, {'properties': {'status': status}})
    assert item['settled'] and item['charge'] == charge


def adapter(state):
    azure = guard.Azure.__new__(guard.Azure)
    azure.worker = '/subscriptions/test/resourceGroups/test/providers/Microsoft.App/jobs/worker'
    azure.blob = Mock()
    azure.blob.acquire_lease.return_value.__enter__ = Mock(return_value='lease')
    azure.blob.acquire_lease.return_value.__exit__ = Mock(return_value=False)
    azure.blob.download_blob.return_value.readall.return_value = json.dumps(state)
    azure.queue = Mock()
    azure.queue.peek_messages.return_value = [object()]
    azure.cost = Mock(return_value=5)
    azure.arm = Mock()
    return azure


def valid_job():
    return {'properties': {'workloadProfileName': 'Consumption', 'configuration': {
        'triggerType': 'Manual', 'replicaRetryLimit': 0,
        'manualTriggerConfig': {'parallelism': 1, 'replicaCompletionCount': 1}},
        'template': {'containers': [{'name': 'worker', 'imageType': 'ContainerImage', 'resources': {'cpu': 4, 'memory': '8Gi'},
            'command': ['python', '-m', 'poligrapher_app.cost_worker'], 'env': []}]}}}


def test_persists_reservation_before_start_and_overrides_runtime():
    state = ledger()
    state['month'] = datetime.now(timezone.utc).strftime('%Y-%m')
    azure = adapter(state)
    def arm(method, path, body=None):
        if method == 'GET':
            return valid_job()
        saved = json.loads(azure.blob.upload_blob.call_args.args[0])
        assert saved['reservations'][-1]['execution'] is None
        env = body['containers'][0]['env']
        assert 'imageType' not in body['containers'][0]
        assert int(env[-1]['value']) == saved['reservations'][-1]['seconds']
        return {'name': 'execution-1'}
    azure.arm.side_effect = arm
    azure.dispatch()
    saved = json.loads(azure.blob.upload_blob.call_args.args[0])
    assert saved['reservations'][-1]['execution'] == 'execution-1'


def test_uncertain_start_remains_reserved_and_blocks_retry():
    state, _ = guard.reserve(ledger(), NOW, 5)
    azure = adapter(state)
    azure.dispatch()
    azure.arm.assert_not_called()
    saved = json.loads(azure.blob.upload_blob.call_args.args[0])
    assert saved['paused'] and saved['reservations'][0]['charge'] > 0


def test_failed_ledger_write_never_starts_worker():
    azure = adapter(ledger())
    azure.blob.upload_blob.side_effect = RuntimeError('storage unavailable')
    with pytest.raises(RuntimeError):
        azure.dispatch()
    azure.arm.assert_not_called()


def test_no_visible_queue_never_starts_worker_or_queries_costs():
    azure = adapter(ledger())
    azure.queue.peek_messages.return_value = []
    azure.dispatch()
    azure.arm.assert_not_called()
    azure.cost.assert_not_called()


def test_missing_ledger_fails_closed():
    azure = adapter(ledger())
    azure.blob.download_blob.side_effect = RuntimeError('missing ledger')
    with pytest.raises(RuntimeError):
        azure.dispatch()
    azure.arm.assert_not_called()


def test_runtime_guard_terminates_hung_child():
    assert run_bounded([sys.executable, '-c', 'import time; time.sleep(30)'], 0.1) == 124


def test_runtime_guard_preserves_exit_code():
    assert run_bounded([sys.executable, '-c', 'raise SystemExit(7)'], 5) == 7
