import type {
  CapturedPolicyText,
  Assessments,
  BulkActionPreview,
  BulkOperation,
  GraphElements,
  GraphStats,
  ImportSummary,
  Provider,
  CompanyCatalogSearch,
  CompanyCollection,
  IndexSyncSummary,
  RunGroup,
  RerunAvailability,
  Schedule,
  SourcePreview,
  TaskStatus,
  TaskOutput,
  RetentionPreview,
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
  listIndustries: () => request<string[]>("/api/providers/industries"),
  searchCompanyCatalog: (query: string) =>
    request<CompanyCatalogSearch>(`/api/providers/catalog/search?q=${encodeURIComponent(query)}`),
  createProvider: (body: {
    name: string;
    industry: string | null;
    domain?: string | null;
    source_url?: string | null;
  }) =>
    request<Provider>("/api/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteProvider: (id: string) =>
    request<void>(`/api/providers/${id}`, { method: "DELETE" }),
  importCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportSummary>("/api/providers/import", { method: "POST", body: form });
  },

  // Company collections
  listCollections: () => request<CompanyCollection[]>("/api/collections"),
  createCollection: (body: { name: string; description?: string | null; provider_ids: string[] }) =>
    request<CompanyCollection>("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateCollection: (id: string, body: Partial<{ name: string; description: string | null; provider_ids: string[] }>) =>
    request<CompanyCollection>(`/api/collections/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteCollection: (id: string) =>
    request<void>(`/api/collections/${id}`, { method: "DELETE" }),
  syncSp500: () =>
    request<IndexSyncSummary>("/api/collections/sp500/sync", { method: "POST" }),
  verifyCollectionSources: (id: string) =>
    request<TaskStatus>(`/api/collections/${id}/verify-sources`, { method: "POST" }),
  recoverCollectionFailures: (id: string) =>
    request<TaskStatus>(`/api/collections/${id}/recover-failures`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deep: true }),
    }),
  analyzeCollection: (id: string) =>
    request<TaskStatus>(`/api/collections/${id}/runs`, { method: "POST" }),

  // Policies
  refreshAll: () => request<TaskStatus>("/api/refresh", { method: "POST" }),
  scoreAll: () => request<TaskStatus>("/api/score-all", { method: "POST" }),
  previewBulkAction: (body: {
    operation: BulkOperation;
    provider_ids: string[];
    collection_ids: string[];
  }) =>
    request<BulkActionPreview>("/api/bulk/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  runBulkAction: (body: {
    operation: BulkOperation;
    provider_ids: string[];
    collection_ids: string[];
  }) =>
    request<TaskStatus>("/api/bulk/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  previewRetention: (older_than_days: number) =>
    request<RetentionPreview>("/api/retention/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ older_than_days }),
    }),
  cleanupRetention: (older_than_days: number) =>
    request<TaskStatus>("/api/retention/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ older_than_days, confirmed: true }),
    }),

  // Provider runs & source
  setSource: (providerId: string, source_url: string) =>
    request<Provider>(`/api/providers/${providerId}/source`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url }),
    }),
  verifyProviderSource: (providerId: string) =>
    request<Provider>(`/api/providers/${providerId}/verify-source`, { method: "POST" }),
  listRuns: (providerId: string) => request<RunGroup[]>(`/api/providers/${providerId}/runs`),
  getRerunAvailability: (providerId: string, runId: string) =>
    request<RerunAvailability>(`/api/providers/${providerId}/runs/${runId}/rerun-availability`),
  rerun: (providerId: string, runId: string) =>
    request<TaskStatus>(`/api/providers/${providerId}/runs/${runId}/rerun`, { method: "POST" }),
  deleteRun: (providerId: string, runId: string) =>
    request<void>(`/api/providers/${providerId}/runs/${runId}`, { method: "DELETE" }),
  runNow: (providerId: string) =>
    request<TaskStatus>(`/api/providers/${providerId}/runs`, { method: "POST" }),
  uploadPdf: (providerId: string, file: File) => {
    const form = new FormData();
    form.append("pdf_file", file);
    return request<TaskStatus>(`/api/providers/${providerId}/uploads`, { method: "POST", body: form });
  },
  uploadCapturedText: (providerId: string, capture: CapturedPolicyText) =>
    request<TaskStatus>(`/api/providers/${providerId}/text-uploads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(capture),
    }),
  toggleSchedule: (providerId: string, enabled: boolean, cadence?: string) =>
    request<Schedule>(`/api/providers/${providerId}/schedule`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, cadence }),
    }),

  // Schedules
  listAllSchedules: () => request<Schedule[]>("/api/schedules"),
  listSchedules: (providerId: string) =>
    request<Schedule[]>(`/api/providers/${providerId}/schedules`),
  sourcePreview: (providerId: string) =>
    request<SourcePreview>(`/api/providers/${providerId}/source-preview`),

  // Analysis
  listTasks: () => request<TaskStatus[]>("/api/tasks"),
  getTask: (taskId: string) => request<TaskStatus>(`/api/tasks/${taskId}`),
  getTaskOutput: (taskId: string) => request<TaskOutput>(`/api/tasks/${taskId}/output`),
  cancelTask: (taskId: string) =>
    request<TaskStatus>(`/api/tasks/${taskId}/cancel`, { method: "POST" }),
  retryTaskFailures: (taskId: string) =>
    request<TaskStatus>(`/api/tasks/${taskId}/retry-failures`, { method: "POST" }),
  getGraph: (id: string) => request<GraphElements>(`/api/policies/${id}/graph`),
  getStats: (id: string) => request<GraphStats>(`/api/policies/${id}/stats`),
  getAssessments: (id: string) => request<Assessments>(`/api/policies/${id}/assessments`),
};
