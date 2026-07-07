import { useQueries, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { TaskStatus } from "../api/types";

/**
 * Runs per-policy tasks (generate/score) with independent concurrency: several
 * policies can have a task in flight at the same time. Each policy is guarded
 * against double-starting its own task, but different policies don't block each
 * other. Returns `runningIds` (policies with an active task) and `start`.
 */
export function usePolicyTasks(providerId: string | null) {
  const qc = useQueryClient();
  // policyId -> in-flight taskId
  const [tasks, setTasks] = useState<Record<string, string>>({});
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  const entries = Object.entries(tasks);

  const results = useQueries({
    queries: entries.map(([, taskId]) => ({
      queryKey: ["task", taskId],
      queryFn: () => api.getTask(taskId),
      refetchInterval: (query: { state: { data?: TaskStatus } }) => {
        const status = query.state.data?.status;
        return status === "done" || status === "failed" ? false : 1500;
      },
    })),
  });

  useEffect(() => {
    for (const result of results) {
      const task = result.data;
      if (!task || (task.status !== "done" && task.status !== "failed")) continue;

      const entry = Object.entries(tasksRef.current).find(([, id]) => id === task.task_id);
      if (!entry) continue;
      const [policyId] = entry;

      if (providerId) qc.invalidateQueries({ queryKey: ["policies", providerId] });
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["graph", policyId] });
      qc.invalidateQueries({ queryKey: ["stats", policyId] });
      qc.invalidateQueries({ queryKey: ["assessments", policyId] });

      setTasks((prev) => {
        const next = { ...prev };
        delete next[policyId];
        return next;
      });
    }
  }, [results, providerId, qc]);

  const start = useCallback(
    async (policyId: string, action: (id: string) => Promise<TaskStatus>) => {
      if (tasksRef.current[policyId]) return; // this policy already has a task running
      const started = await action(policyId);
      setTasks((prev) => ({ ...prev, [policyId]: started.task_id }));
    },
    [],
  );

  return { start, runningIds: new Set(Object.keys(tasks)) };
}
