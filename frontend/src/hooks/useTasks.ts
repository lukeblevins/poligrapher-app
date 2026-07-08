import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { isTaskActive } from "../api/types";

/**
 * Global view of all backend tasks (per-policy generate/score and bulk
 * refresh/score-all), used by the Status Center. Polls while any task is
 * active and stops once everything has settled.
 */
export function useTasks() {
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.listTasks,
    refetchInterval: (query) => {
      const list = query.state.data ?? [];
      return list.some((t) => isTaskActive(t.status)) ? 1500 : false;
    },
  });

  const activeCount = tasks.filter((t) => isTaskActive(t.status)).length;
  return { tasks, activeCount, isLoading };
}

export function useCancelTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => api.cancelTask(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["policies"] });
    },
  });
}
