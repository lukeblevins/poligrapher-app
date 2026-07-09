import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { RunGroup } from "../api/types";

/** Runs for a provider; polls while any run is still generating. */
export function useRuns(providerId: string | null) {
  return useQuery({
    queryKey: ["runs", providerId],
    queryFn: () => api.listRuns(providerId!),
    enabled: !!providerId,
    refetchInterval: (query) => {
      const groups = (query.state.data ?? []) as RunGroup[];
      const pending = groups.some((g) => g.runs.some((r) => r.pipeline_status === "pending"));
      return pending ? 2500 : false;
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
  return {
    setSource: useMutation({
      mutationFn: (url: string) => api.setSource(providerId, url),
      onSuccess: invalidate,
    }),
    runNow: useMutation({
      mutationFn: () => api.runNow(providerId),
      onSuccess: invalidate,
    }),
    upload: useMutation({
      mutationFn: (file: File) => api.uploadPdf(providerId, file),
      onSuccess: invalidate,
    }),
    toggle: useMutation({
      mutationFn: ({ enabled, cadence }: { enabled: boolean; cadence?: string }) =>
        api.toggleSchedule(providerId, enabled, cadence),
      onSuccess: invalidate,
    }),
  };
}
