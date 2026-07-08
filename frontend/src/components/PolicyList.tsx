import { useState } from "react";

import { api } from "../api/client";
import type { Policy, Provider } from "../api/types";
import { useDeletePolicy, usePolicies } from "../hooks/queries";
import { usePolicyTasks } from "../hooks/usePolicyTasks";
import { AddPolicyModal } from "./modals/AddPolicyModal";
import { ScheduleModal } from "./modals/ScheduleModal";

interface Props {
  provider: Provider | null;
  selectedPolicyId: string | null;
  onSelectPolicy: (id: string) => void;
}

const STATUS_STYLES: Record<string, string> = {
  succeeded: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
};

export function PolicyList({ provider, selectedPolicyId, onSelectPolicy }: Props) {
  const { data: policies = [], isLoading } = usePolicies(provider?.id ?? null);
  const deletePolicy = useDeletePolicy(provider?.id ?? "");
  const [showAdd, setShowAdd] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);

  // Per-policy tasks run concurrently; only the policy's own buttons disable
  // while its task is in flight.
  const { start: runPolicyTask, runningIds } = usePolicyTasks(provider?.id ?? null);

  function runAction(policy: Policy, action: (id: string) => Promise<any>) {
    runPolicyTask(policy.id, action);
  }

  if (!provider) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400 dark:text-zinc-500">
        <p>Select a company to view its policies.</p>
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 overflow-auto p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">{provider.name}</h1>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setShowSchedule(true)}>
            Schedule
          </button>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>
            + Policy
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : policies.length === 0 ? (
        <p className="text-sm text-zinc-400">No policies yet. Add one to get started.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
              <th className="py-2 pr-2 font-medium">Source</th>
              <th className="py-2 pr-2 font-medium">Date</th>
              <th className="py-2 pr-2 font-medium">Status</th>
              <th className="py-2 pr-2 font-medium">Privacy</th>
              <th className="py-2 pr-2 font-medium">GDPR</th>
              <th className="py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => (
              <tr
                key={p.id}
                onClick={() => onSelectPolicy(p.id)}
                className={`cursor-pointer border-b border-zinc-100 dark:border-zinc-800 ${
                  selectedPolicyId === p.id
                    ? "bg-indigo-50 dark:bg-indigo-950/50"
                    : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
                }`}
              >
                <td className="py-2 pr-2 capitalize">{p.source}</td>
                <td className="py-2 pr-2 text-zinc-500 dark:text-zinc-400">
                  {p.capture_date ?? "—"}
                </td>
                <td className="py-2 pr-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      STATUS_STYLES[p.pipeline_status] ?? ""
                    }`}
                  >
                    {runningIds.has(p.id) ? "running…" : p.pipeline_status}
                  </span>
                </td>
                <td className="py-2 pr-2">{p.privacy_score?.toFixed(1) ?? "—"}</td>
                <td className="py-2 pr-2">{p.gdpr_score?.toFixed(1) ?? "—"}</td>
                <td className="py-2" onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1">
                    <button
                      className="btn-secondary px-2 py-1 text-xs"
                      disabled={runningIds.has(p.id)}
                      onClick={() => runAction(p, api.generate)}
                    >
                      Generate
                    </button>
                    <button
                      className="btn-secondary px-2 py-1 text-xs"
                      disabled={runningIds.has(p.id) || p.pipeline_status !== "succeeded"}
                      onClick={() => runAction(p, api.score)}
                    >
                      Score
                    </button>
                    <button
                      className="btn-secondary px-2 py-1 text-xs text-red-600 dark:text-red-400"
                      onClick={() => {
                        if (confirm("Delete this policy?")) deletePolicy.mutate(p.id);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAdd && <AddPolicyModal providerId={provider.id} onClose={() => setShowAdd(false)} />}
      {showSchedule && <ScheduleModal provider={provider} onClose={() => setShowSchedule(false)} />}
    </div>
  );
}
