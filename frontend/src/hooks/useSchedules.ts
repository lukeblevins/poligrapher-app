import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export function useSchedules(providerId: string | null) {
  return useQuery({
    queryKey: ["schedules", providerId],
    queryFn: () => api.listSchedules(providerId!),
    enabled: !!providerId,
  });
}
