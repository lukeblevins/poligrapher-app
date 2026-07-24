import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { RunGroup } from "../api/types";

/** Runs for a provider; polls while any run is still generating. */
export function useRuns(providerId: string | null, pollForTasks = false) {
  return useQuery({
    queryKey: ["runs", providerId],
    queryFn: () => api.listRuns(providerId!),
    enabled: !!providerId,
    refetchInterval: (query) => {
      const groups = (query.state.data ?? []) as RunGroup[];
      const pending = groups.some((g) => g.runs.some((r) => r.pipeline_status === "pending"));
      return pending || pollForTasks ? 1500 : false;
    },
  });
}

/** Mutations for a provider's source, runs, uploads, and schedule toggle. */
export function useRunActions(providerId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["runs", providerId] });
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["schedules", providerId] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };
  const registerTask = (task: import("../api/types").TaskStatus) => {
    qc.setQueryData<import("../api/types").TaskStatus[]>(["tasks"], (current = []) => [
      task,
      ...current.filter((candidate) => candidate.task_id !== task.task_id),
    ]);
    invalidate();
  };
  return {
    setSource: useMutation({
      mutationFn: (url: string) => api.setSource(providerId, url),
      onSuccess: invalidate,
    }),
    verifySource: useMutation({
      mutationFn: () => api.verifyProviderSource(providerId),
      onSuccess: invalidate,
    }),
    previewSource: useMutation({
      mutationFn: () => api.sourcePreview(providerId),
    }),
    runNow: useMutation({
      mutationFn: () => api.runNow(providerId),
      onSuccess: registerTask,
    }),
    upload: useMutation({
      mutationFn: (file: File) => api.uploadPdf(providerId, file),
      onSuccess: registerTask,
    }),
    rerun: useMutation({
      mutationFn: (runId: string) => api.rerun(providerId, runId),
      onSuccess: registerTask,
    }),
    deleteRun: useMutation({
      mutationFn: (runId: string) => api.deleteRun(providerId, runId),
      onSuccess: invalidate,
    }),
    toggle: useMutation({
      mutationFn: ({ enabled, cadence }: { enabled: boolean; cadence?: string }) =>
        api.toggleSchedule(providerId, enabled, cadence),
      onSuccess: invalidate,
    }),
  };
}
