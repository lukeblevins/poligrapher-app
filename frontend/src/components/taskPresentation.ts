import type { TaskStatus } from "../api/types";
import { isTaskActive } from "../api/types";

export type TaskPresentation = {
  operation: string;
  target: string | null;
};

const OPERATION_LABELS: Record<string, string> = {
  comparison: "Company analysis",
  "rerun-comparison": "Company analysis",
  upload: "PDF analysis",
  "rerun-upload": "PDF analysis",
  generate: "Policy analysis",
  "bulk-generate": "Company analysis",
  "collection-analysis": "Company analysis",
  score: "Score analysis",
  "bulk-score": "Score analyses",
  refresh: "Refresh analyses",
  "source-verification": "Source verification",
  "cohort-source-audit": "Source audit",
  "cohort-recovery": "Coverage recovery",
  "retention-cleanup": "Retention cleanup",
  schedule: "Scheduled analysis",
};

const LEGACY_TITLE_SEPARATOR = /\s+·\s+/;

function legacyTarget(task: TaskStatus): string | null {
  const title = task.title ?? task.label;
  if (!title) return null;
  const parts = title.split(LEGACY_TITLE_SEPARATOR);
  return parts.length > 1 ? parts.slice(1).join(" ").trim() || null : null;
}

function fallbackOperation(task: TaskStatus): string {
  const title = task.title ?? task.label;
  if (title) return title.split(LEGACY_TITLE_SEPARATOR)[0].trim();
  if (task.kind) {
    return task.kind
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }
  return "Task";
}

export function taskPresentation(task: TaskStatus): TaskPresentation {
  const operation = (task.kind && OPERATION_LABELS[task.kind]) || fallbackOperation(task);
  const target = task.provider_name
    || legacyTarget(task)
    || (task.total > 0 && ["bulk-generate", "bulk-score", "collection-analysis", "cohort-recovery"].includes(task.kind ?? "")
      ? `${task.total} ${task.kind === "bulk-score" ? (task.total === 1 ? "policy" : "policies") : (task.total === 1 ? "company" : "companies")}`
      : null);
  return { operation, target };
}

export type TaskProgress = {
  completed: number;
  total: number;
  percentage: number;
  value: number;
  text: string;
} | null;

export function taskProgress(task: TaskStatus): TaskProgress {
  if (!isTaskActive(task.status) || !Number.isFinite(task.total) || task.total <= 0) return null;
  const total = Math.max(0, Math.trunc(task.total));
  if (total === 0) return null;
  const completed = Math.min(total, Math.max(0, Number.isFinite(task.completed) ? Math.trunc(task.completed) : 0));
  const value = completed / total;
  const percentage = Math.round(value * 100);
  return {
    completed,
    total,
    percentage,
    value,
    text: `${completed} of ${total} (${percentage}%)`,
  };
}
