import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";

// ── Queries ──────────────────────────────────────────────────────────────────

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
}

export function useCollections() {
  return useQuery({ queryKey: ["collections"], queryFn: api.listCollections });
}

export function usePolicies(providerId: string | null) {
  return useQuery({
    queryKey: ["policies", providerId],
    queryFn: () => api.listPolicies(providerId!),
    enabled: !!providerId,
  });
}

export function useGraph(policyId: string | null) {
  return useQuery({
    queryKey: ["graph", policyId],
    queryFn: () => api.getGraph(policyId!),
    enabled: !!policyId,
    retry: false,
  });
}

export function useStats(policyId: string | null) {
  return useQuery({
    queryKey: ["stats", policyId],
    queryFn: () => api.getStats(policyId!),
    enabled: !!policyId,
    retry: false,
  });
}

export function useAssessments(policyId: string | null) {
  return useQuery({
    queryKey: ["assessments", policyId],
    queryFn: () => api.getAssessments(policyId!),
    enabled: !!policyId,
    retry: false,
  });
}

// ── Mutations ────────────────────────────────────────────────────────────────

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name: string;
      industry: string | null;
      domain?: string | null;
      source_url?: string | null;
    }) => api.createProvider(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useImportCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.importCsv(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useAddPolicy(providerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => api.addPolicy(providerId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["policies", providerId] });
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
  });
}

export function useDeletePolicy(providerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deletePolicy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["policies", providerId] });
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
  });
}
