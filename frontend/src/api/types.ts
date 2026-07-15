// Response types mirroring poligrapher_app/api/schemas.py

export interface Provider {
  id: string;
  name: string;
  industry: string | null;
  domain: string | null;
  source_url: string | null;
  ticker: string | null;
  tickers: string[];
  cik: string | null;
  source_status: "unchecked" | "available" | "restricted" | "broken" | "error" | "missing";
  source_checked_at: string | null;
  source_http_status: number | null;
  source_final_url: string | null;
  collection_ids: string[];
  created_at: string;
  policy_count: number;
  succeeded_count: number;
  failed_count: number;
}

export interface CompanyCollection {
  id: string;
  name: string;
  description: string | null;
  kind: "system" | "custom";
  source_url: string | null;
  snapshot_date: string | null;
  provider_ids: string[];
  provider_count: number;
  created_at: string;
}

export interface IndexSyncSummary {
  collection_id: string;
  securities: number;
  companies: number;
  created: number;
  updated: number;
  snapshot_date: string;
}

export interface CompanyCatalogResult {
  id: string;
  name: string;
  domain: string | null;
  source_url: string;
  source: "open_terms_archive";
  attribution_url: string;
  requires_javascript: boolean;
}

export interface CompanyCatalogSearch {
  results: CompanyCatalogResult[];
  source_available: boolean;
}

export interface RunGroup {
  run_id: string;
  run_group: string | null;
  kind: "comparison" | "upload" | "legacy";
  scheduled: boolean;
  capture_date: string | null;
  created_at: string;
  runs: Policy[];
  task: TaskStatus | null;
}

export interface Schedule {
  id: string;
  provider_id: string;
  cadence: string;
  enabled: boolean;
  source_override_url: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string;
  last_source_url: string | null;
  last_strategy: string | null;
  last_confidence: number | null;
  last_content_hash: string | null;
  needs_attention: boolean;
  created_at: string;
}

export interface SourcePreview {
  url: string | null;
  strategy: string | null;
  confidence: number;
  auto: boolean;
  select: unknown | null;
  notes: string;
  resolved: boolean;
}

export interface PipelineError {
  message: string;
  timestamp?: string;
}

export interface Policy {
  id: string;
  provider_id: string;
  url: string;
  source: "webpage" | "pdf";
  method: "website" | "pdf_from_page" | "pdf_upload";
  run_group: string | null;
  scheduled: boolean;
  content_hash: string | null;
  capture_date: string | null;
  has_results: boolean;
  pipeline_status: "pending" | "succeeded" | "failed";
  pipeline_errors: PipelineError[];
  privacy_score: number | null;
  gdpr_score: number | null;
  graph_kind: string;
  created_at: string;
}

export type TaskState = "running" | "cancelling" | "cancelled" | "done" | "failed";

export interface TaskStatus {
  task_id: string;
  status: TaskState;
  error: string | null;
  label: string | null;
  title?: string | null;
  kind?: string | null;
  total: number;
  completed: number;
  failed: number;
  created_at?: string | null;
  started_at?: string | null;
  cancelable?: boolean;
  policy_id?: string | null;
  provider_id?: string | null;
  run_id?: string | null;
  provider_name?: string | null;
  has_output?: boolean;
}

export interface TaskOutput {
  task_id: string;
  status: TaskState;
  output: string;
  truncated: boolean;
}

export const TASK_ACTIVE_STATES: TaskState[] = ["running", "cancelling"];

export function isTaskActive(status: TaskState): boolean {
  return status === "running" || status === "cancelling";
}

const RUN_TASK_KINDS = new Set([
  "comparison",
  "upload",
  "rerun-upload",
  "rerun-comparison",
  "generate",
  "score",
  "schedule",
]);

export function isRunTask(task: TaskStatus): boolean {
  return !!task.run_id || (!!task.kind && RUN_TASK_KINDS.has(task.kind));
}

export function isTaskSettled(status: TaskState): boolean {
  return status === "done" || status === "failed" || status === "cancelled";
}

export interface ImportSummary {
  created: number;
  skipped: number;
  errors: number;
}

// ── Graph ────────────────────────────────────────────────────────────────────

export interface CytoscapeElement {
  data: {
    id: string;
    label?: string;
    type?: string;
    source?: string;
    target?: string;
  };
}

export interface GraphElements {
  elements: CytoscapeElement[];
}

// ── Statistics ───────────────────────────────────────────────────────────────

export interface DegreeStats {
  min: number;
  max: number;
  mean: number;
  median: number;
}

export interface GraphStatsData {
  node_count: number;
  edge_count: number;
  node_type_counts: Record<string, number>;
  edge_type_counts: Record<string, number>;
  degree: DegreeStats;
  in_degree: DegreeStats;
  out_degree: DegreeStats;
  density: number;
  average_clustering: number;
  transitivity: number;
  component_count: number;
  largest_component_size: number;
  largest_component_ratio: number;
  average_shortest_path_largest_component: number | null;
  isolated_nodes: number;
  self_loop_count: number;
  top_degree_nodes: [string, number][];
  top_in_degree_nodes: [string, number][];
  top_out_degree_nodes: [string, number][];
}

export interface GraphStats {
  stats: GraphStatsData | null;
}

// ── Assessments ──────────────────────────────────────────────────────────────

export interface PrivacyCategoryScore {
  raw_score: number;
  weighted_score: number;
  feedback: string[];
}

export interface PrivacyAssessment {
  success: boolean;
  total_score: number;
  grade: string;
  summary: string;
  category_scores: Record<string, PrivacyCategoryScore>;
}

export interface ComponentScore {
  score: number;
  weight: number;
}

export interface Violation {
  code: string;
  rq: string;
  rq_label?: string;
  article?: string;
  severity: string;
  scope?: string;
  description?: string;
  detail?: string;
}

export interface GdprAssessment {
  success: boolean;
  total_score?: number;
  normalized_score?: number;
  tier?: string;
  summary?: string;
  component_scores?: Record<string, ComponentScore>;
  severity_counts?: Record<string, number>;
  flags?: string[];
  feature_summary?: Record<string, number>;
  top_violations?: Record<string, Violation[]>;
  feedback?: string[];
}

export interface Readability {
  flesch_kincaid: number;
  gunning_fog: number;
  flesch_reading_ease: number;
  n_words: number;
  n_sentences: number;
  passive_ratio: number;
}

export interface Assessments {
  privacy: PrivacyAssessment | null;
  gdpr: GdprAssessment | null;
  readability: Readability | null;
}
