"""Fail-closed dispatcher for the manual Azure analysis job.

An operator initializes cost-control/ledger.json before enabling this job.
Never recreate a missing ledger: losing it must not replenish the allowance.
One blob lease serializes reservation and dispatch. An uncertain start retains
its full reservation and blocks further dispatch until an operator reconciles it.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from azure.core.credentials import AccessToken
from azure.storage.blob import BlobClient
from azure.storage.queue import QueueClient

API_VERSION = "2025-07-01"
ARM = "https://management.azure.com"
# East US 2: 4 vCPU * $0.000024 + 8 GiB * $0.000003 = $0.000120/s.
# Reserve 25% extra, ignore free grants, and charge five minutes for startup.
RATE = 0.000150
STARTUP_SECONDS = 300
MAX_SECONDS = 43200
MIN_SECONDS = 900
ALLOWANCE = 10.0
BILLING_STOP = 28.0


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def reserve(state: dict, now: datetime, reported_cost: float) -> tuple[dict, dict | None]:
    """Reserve before any start request; callers persist this result first."""
    result = copy.deepcopy(state)
    if result["version"] != 1 or result["allowance"] != ALLOWANCE:
        raise ValueError("Unexpected ledger version or allowance; operator review required")
    if result.get("paused"):
        return result, None
    if result["month"] != now.strftime("%Y-%m"):
        result.update(paused=True, reason="New month: review and explicitly renew allowance")
        return result, None
    if reported_cost >= BILLING_STOP:
        result.update(paused=True, reason="Reported resource-group cost reached $28")
        return result, None
    if any(not item.get("settled") for item in result["reservations"]):
        return result, None
    used = sum(item["charge"] for item in result["reservations"]) + result["initial_spend"]
    if not 0 <= used <= ALLOWANCE + 0.000001:
        raise ValueError("Invalid ledger balance")
    seconds = min(MAX_SECONDS, int((ALLOWANCE - used) / RATE) - STARTUP_SECONDS)
    # Do not authorize an execution across a month boundary.
    next_month = now.replace(day=28) + timedelta(days=4)
    boundary = next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seconds = min(seconds, int((boundary - now).total_seconds()) - STARTUP_SECONDS)
    if seconds < MIN_SECONDS:
        result.update(paused=True, reason="Compute allowance exhausted or month boundary reached")
        return result, None
    item = {"id": str(uuid.uuid4()), "reserved_at": now.isoformat(),
            "seconds": seconds, "charge": (seconds + STARTUP_SECONDS) * RATE,
            "execution": None, "settled": False}
    result["reservations"].append(item)
    result["reason"] = "Runtime reserved before dispatch"
    return result, item


def settle(item: dict, execution: dict) -> None:
    """Refund only a proven successful execution; failures keep the full charge."""
    props = execution["properties"]
    status = props["status"]
    if status not in ("Succeeded", "Failed", "Stopped"):
        return
    if status == "Succeeded" and props.get("startTime") and props.get("endTime"):
        elapsed = (stamp(props["endTime"]) - stamp(props["startTime"])).total_seconds()
        if elapsed < 0:
            raise ValueError("Execution end precedes start")
        item["charge"] = min(item["charge"], (elapsed + STARTUP_SECONDS) * RATE)
    item.update(settled=True, status=status)


class Identity:
    """Container Apps managed identity endpoint; no stored credentials."""

    def __init__(self):
        self.cache = {}

    def get_token(self, *scopes, **kwargs):
        resource = scopes[0].removesuffix("/.default")
        token = self.cache.get(resource)
        if token and token.expires_on > time.time() + 120:
            return token
        response = requests.get(
            os.environ["IDENTITY_ENDPOINT"],
            headers={"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]},
            params={"resource": resource, "api-version": "2019-08-01",
                    "client_id": os.environ["AZURE_CLIENT_ID"]}, timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        token = AccessToken(data["access_token"], int(data["expires_on"]))
        self.cache[resource] = token
        return token


class Azure:
    def __init__(self):
        self.identity = Identity()
        self.worker = os.environ["COST_WORKER_ID"]
        self.group = self.worker.split("/providers/")[0]
        account = os.environ["COST_STORAGE_ACCOUNT"]
        self.blob = BlobClient(
            f"https://{account}.blob.core.windows.net", "poligrapher-cost-control", "ledger.json",
            credential=self.identity, retry_total=0, connection_timeout=8, read_timeout=8,
        )
        self.queue = QueueClient(
            f"https://{account}.queue.core.windows.net", "analysis-tasks",
            credential=self.identity, retry_total=0, connection_timeout=8, read_timeout=8,
        )

    def arm(self, method, path, body=None):
        token = self.identity.get_token(ARM + "/.default").token
        response = requests.request(method, ARM + path,
            headers={"Authorization": "Bearer " + token,
                     "ClientType": "GitHubCopilotForAzure"}, json=body, timeout=8)
        response.raise_for_status()
        return response.json() if response.content else {}

    def cost(self, state, now):
        cached = state.get("billing")
        if cached and 0 <= (now - stamp(cached["checked_at"])).total_seconds() < 3600:
            return cached["amount"]
        data = self.arm("POST", self.group +
            "/providers/Microsoft.CostManagement/query?api-version=2023-11-01", {
                "type": "ActualCost", "timeframe": "MonthToDate",
                "dataset": {"granularity": "None", "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"}}}})
        props = data["properties"]
        columns = [c["name"] for c in props["columns"]]
        if props.get("nextLink") or not props["rows"]:
            raise ValueError("Incomplete billing result")
        if any(r[columns.index("Currency")] != "USD" for r in props["rows"]):
            raise ValueError("Budget requires USD billing")
        amount = sum(r[columns.index("Cost")] for r in props["rows"])
        if amount < 0:
            raise ValueError("Unexpected negative cost")
        state["billing"] = {"amount": amount, "checked_at": now.isoformat()}
        return amount

    def dispatch(self):
        now = datetime.now(timezone.utc)
        with self.blob.acquire_lease(lease_duration=60) as lease:
            state = json.loads(self.blob.download_blob(lease=lease).readall())
            if state.get("paused"):
                print("Analysis paused:", state.get("reason"), flush=True)
                return
            outstanding = [r for r in state["reservations"] if not r.get("settled")]
            for item in outstanding:
                if not item.get("execution"):
                    # A timeout after submitting a start is ambiguous. Never retry it.
                    state.update(paused=True, reason="Uncertain dispatch requires reconciliation")
                    self.save(state, lease)
                    return
                execution = self.arm("GET", self.worker + "/executions/" +
                                     item["execution"] + "?api-version=" + API_VERSION)
                settle(item, execution)
            self.save(state, lease)
            if any(not r.get("settled") for r in state["reservations"]):
                print("An authorized worker is still active", flush=True)
                return
            if not list(self.queue.peek_messages(max_messages=1)):
                print("No visible analysis messages; no worker started", flush=True)
                return
            reported = self.cost(state, now)
            job = self.arm("GET", self.worker + "?api-version=" + API_VERSION)
            props = job["properties"]
            config = props["configuration"]
            containers = props["template"]["containers"]
            if (config["triggerType"] != "Manual" or config["replicaRetryLimit"] != 0
                    or config["manualTriggerConfig"] != {"parallelism": 1, "replicaCompletionCount": 1}
                    or props.get("workloadProfileName") != "Consumption"
                    or len(containers) != 1 or props["template"].get("initContainers")
                    or containers[0]["resources"]["cpu"] != 4
                    or containers[0]["resources"]["memory"] != "8Gi"
                    or containers[0].get("command") != ["python", "-m", "poligrapher_app.cost_worker"]):
                raise ValueError("Worker configuration differs from cost assumptions")
            state, item = reserve(state, now, reported)
            self.save(state, lease)
            if item is None:
                print("No dispatch:", state.get("reason"), flush=True)
                return
            template = copy.deepcopy(props["template"])
            container = template["containers"][0]
            container["env"] = [e for e in container.get("env", [])
                                if e["name"] != "COST_MAX_RUNTIME_SECONDS"]
            container["env"].append({"name": "COST_MAX_RUNTIME_SECONDS", "value": str(item["seconds"])})
            # No HTTP retries: reserve first; ambiguous starts remain charged and block.
            started = self.arm("POST", self.worker + "/start?api-version=" + API_VERSION, template)
            item["execution"] = started.get("name")
            if not item["execution"]:
                state.update(paused=True, reason="Start accepted without execution name; reconcile before resuming")
            self.save(state, lease)
            print("Reserved", round(item["charge"], 4), "USD; execution", item["execution"], flush=True)

    def save(self, state, lease):
        self.blob.upload_blob(json.dumps(state), overwrite=True, lease=lease)

    def verify(self):
        """Exercise live identity, billing, ledger and queue reads without dispatch."""
        state = json.loads(self.blob.download_blob().readall())
        state.pop("billing", None)
        amount = self.cost(state, datetime.now(timezone.utc))
        job = self.arm("GET", self.worker + "?api-version=" + API_VERSION)
        print(json.dumps({"month": state["month"], "allowance": state["allowance"],
            "paused": state["paused"], "reported_cost": amount,
            "visible_message": bool(list(self.queue.peek_messages(max_messages=1))),
            "worker_trigger": job["properties"]["configuration"]["triggerType"]}), flush=True)


def main():
    # A separate process enforces a total dispatcher deadline in cost_dispatcher.
    azure = Azure()
    if "--verify" in sys.argv:
        azure.verify()
    else:
        azure.dispatch()


if __name__ == "__main__":
    main()
