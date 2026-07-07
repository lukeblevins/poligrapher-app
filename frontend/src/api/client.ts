import type {
  Assessments,
  GraphElements,
  GraphStats,
  ImportSummary,
  Policy,
  Provider,
  TaskStatus,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // Providers
  listProviders: () => request<Provider[]>("/api/providers"),
  createProvider: (name: string, industry: string | null) =>
    request<Provider>("/api/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, industry }),
    }),
  deleteProvider: (id: string) =>
    request<void>(`/api/providers/${id}`, { method: "DELETE" }),
  importCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportSummary>("/api/providers/import", { method: "POST", body: form });
  },

  // Policies
  listPolicies: (providerId: string) =>
    request<Policy[]>(`/api/providers/${providerId}/policies`),
  addPolicy: (providerId: string, form: FormData) =>
    request<Policy>(`/api/providers/${providerId}/policies`, { method: "POST", body: form }),
  deletePolicy: (id: string) =>
    request<void>(`/api/policies/${id}`, { method: "DELETE" }),
  generate: (id: string) =>
    request<TaskStatus>(`/api/policies/${id}/generate`, { method: "POST" }),
  score: (id: string) =>
    request<TaskStatus>(`/api/policies/${id}/score`, { method: "POST" }),
  refreshAll: () => request<TaskStatus>("/api/refresh", { method: "POST" }),
  scoreAll: () => request<TaskStatus>("/api/score-all", { method: "POST" }),

  // Analysis
  getTask: (taskId: string) => request<TaskStatus>(`/api/tasks/${taskId}`),
  getGraph: (id: string) => request<GraphElements>(`/api/policies/${id}/graph`),
  getStats: (id: string) => request<GraphStats>(`/api/policies/${id}/stats`),
  getAssessments: (id: string) => request<Assessments>(`/api/policies/${id}/assessments`),
};
