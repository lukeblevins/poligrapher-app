import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";

export function useSchedules(providerId: string | null) {
  return useQuery({
    queryKey: ["schedules", providerId],
    queryFn: () => api.listSchedules(providerId!),
    enabled: !!providerId,
  });
}

/** Mutations for a provider's schedules; all invalidate the provider's list. */
export function useScheduleMutations(providerId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["schedules", providerId] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };

  return {
    create: useMutation({
      mutationFn: (body: { cadence: string; enabled: boolean; source_override_url?: string | null }) =>
        api.createSchedule(providerId, body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<{ cadence: string; enabled: boolean; source_override_url: string | null }> }) =>
        api.updateSchedule(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api.deleteSchedule(id),
      onSuccess: invalidate,
    }),
    run: useMutation({
      mutationFn: (id: string) => api.runSchedule(id),
      onSuccess: invalidate,
    }),
    confirm: useMutation({
      mutationFn: ({ id, url }: { id: string; url: string }) => api.confirmSource(id, url),
      onSuccess: invalidate,
    }),
  };
}
