import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Policy, Provider, RunGroup, TaskStatus } from "../api/types";
import { isRunTask } from "../api/types";
import { useSchedules } from "../hooks/useSchedules";
import { useRunActions, useRuns } from "../hooks/useRuns";
import { useTasks } from "../hooks/useTasks";
import { TaskOutputPanel } from "./TaskOutputPanel";
import { OverflowMenu } from "./OverflowMenu";
import { Modal } from "./Modal";
import { Tooltip } from "./Tooltip";

interface Props {
  provider: Provider | null;
  selectedPolicyId: string | null;
  onSelectPolicy: (id: string | null) => void;
  historyTargetTaskId?: string | null;
  historyTargetNonce?: number;
}

const CADENCES = ["daily", "weekly", "monthly"];

const STATUS_STYLES: Record<string, string> = {
  succeeded: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  done: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  running: "bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300",
  cancelling: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  cancelled: "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
};

const METHOD_LABEL: Record<string, string> = {
  website: "Live page extraction",
  pdf_from_page: "Rendered PDF extraction",
  pdf_upload: "Uploaded PDF",
};

const METHOD_DESCRIPTION: Record<string, string> = {
  website: "Generated from the live privacy-policy page",
  pdf_from_page: "Generated from a PDF rendering of the same page",
  pdf_upload: "Generated from a PDF supplied by the researcher",
};

const SOURCE_STATUS_LABEL: Record<string, string> = {
  unchecked: "Not checked",
  available: "Source available",
  restricted: "Access restricted",
  broken: "Source not found",
  error: "Check failed",
  missing: "Source needed",
};

const SOURCE_STATUS_STYLE: Record<string, string> = {
  unchecked: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
  available: "bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-200 dark:bg-teal-950/50 dark:text-teal-300 dark:ring-teal-800",
  restricted: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  broken: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  error: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  missing: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function score(n: number | null): string {
  return n === null || n === undefined ? "—" : n.toFixed(1);
}

function Toggle({ on, onChange, disabled }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-7 w-12 flex-shrink-0 items-center rounded-full border shadow-inner transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${
        on
          ? "border-teal-600 bg-teal-700"
          : "border-slate-300 bg-slate-200 dark:border-slate-600 dark:bg-slate-700"
      }`}
    >
      <span
        className={`grid h-5 w-5 transform place-items-center rounded-full bg-white text-teal-700 shadow ring-1 ring-black/5 transition-transform duration-200 ${
          on ? "translate-x-6" : "translate-x-1"
        }`}
      >
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`h-3 w-3 transition-opacity ${on ? "opacity-100" : "opacity-0"}`}
          aria-hidden="true"
        >
          <path d="m4 8 2.5 2.5L12 5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </button>
  );
}

// ── Run row (one analysis method within a run group) ──────────────────────────

function RunMethodRow({
  run,
  legacy,
  selected,
  onSelect,
}: {
  run: Policy;
  legacy: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const methodLabel = legacy
    ? "Unknown analysis method"
    : METHOD_LABEL[run.method] ?? "Unrecognized analysis method";
  const methodDescription = legacy
    ? "Imported without recorded processing metadata"
    : METHOD_DESCRIPTION[run.method] ?? "No processing metadata recorded";

  return (
    <button
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      aria-label={`${methodLabel}. Privacy score ${score(run.privacy_score)}. GDPR score ${score(run.gdpr_score)}. ${titleCase(run.pipeline_status)}. ${methodDescription}`}
      className={`group grid w-full grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 border-l-2 px-4 py-2.5 text-left text-sm transition-colors ${
        selected
          ? "border-teal-700 bg-teal-50/80 dark:border-teal-400 dark:bg-teal-950/35"
          : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50"
      }`}
    >
      <span className={`min-w-0 truncate font-semibold ${selected ? "text-teal-900 dark:text-teal-100" : ""}`}>
        {methodLabel}
      </span>
      <span className="data-value text-xs text-slate-500 dark:text-slate-300" aria-hidden="true">P {score(run.privacy_score)}</span>
      <span className="data-value text-xs text-slate-500 dark:text-slate-300" aria-hidden="true">G {score(run.gdpr_score)}</span>
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[run.pipeline_status] ?? ""}`}>
        {titleCase(run.pipeline_status)}
      </span>
    </button>
  );
}

function groupStatus(group: RunGroup, task: TaskStatus | null): string {
  if (task && ["running", "cancelling", "cancelled", "failed"].includes(task.status)) return task.status;
  if (group.runs.some((run) => run.pipeline_status === "pending")) return "pending";
  if (group.runs.some((run) => run.pipeline_status === "failed")) return "failed";
  return "succeeded";
}

function RunCard({
  group,
  task,
  outputExpanded,
  onToggleOutput,
  onRerun,
  onDelete,
  actionsBusy,
  selectedPolicyId,
  onSelectPolicy,
}: {
  group: RunGroup;
  task: TaskStatus | null;
  outputExpanded: boolean;
  onToggleOutput: () => void;
  onRerun: () => void;
  onDelete: () => void;
  actionsBusy: boolean;
  selectedPolicyId: string | null;
  onSelectPolicy: (id: string) => void;
}) {
  const date = new Date(group.created_at);
  const title = group.kind === "legacy"
    ? "Legacy analysis"
    : group.kind === "upload"
      ? "Uploaded PDF"
      : "Website comparison";
  const status = groupStatus(group, task);
  const rerun = group.runs.some((run) => run.rerun_of_policy_id);
  const captureText = group.capture_date
    ? new Date(`${group.capture_date}T00:00:00`).toLocaleDateString()
    : "Unknown";
  const canShowOutput = !!task && (task.has_output || ["running", "cancelling", "failed"].includes(task.status));
  const tooltipContent = (
    <>
      <div className="font-semibold text-white">{group.scheduled ? "Automatic" : "Manual"} {title.toLowerCase()}</div>
      <div className="mt-1 text-slate-200">{group.runs.length} {group.runs.length === 1 ? "method" : "methods"} · Started {date.toLocaleString()}</div>
      <div className="text-slate-200">Source captured {captureText}</div>
      <div className="mt-1 font-mono text-slate-300">Run {group.run_id.slice(0, 8)}</div>
    </>
  );

  return (
    <Tooltip content={tooltipContent} side="bottom" align="end">
    <article
      className="group/run relative overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500"
      data-task-id={task?.task_id}
      role="group"
      aria-label={`${title} from ${date.toLocaleDateString()}`}
      tabIndex={0}
    >
      <header className="flex items-center gap-3 bg-slate-50/70 px-4 py-3 dark:bg-slate-900/45">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
            {rerun && <span className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">Re-run</span>}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[status] ?? ""}`}>{titleCase(status)}</span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {group.scheduled ? "Automatic" : "Manual"} · <time dateTime={date.toISOString()}>{date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time>
            {task && task.total > 0 && ["running", "cancelling"].includes(task.status) ? ` · ${task.completed}/${task.total}` : ""}
          </p>
        </div>
        {canShowOutput && (
          <button
            type="button"
            className="btn-secondary min-h-8 shrink-0 px-2.5 py-1 text-xs"
            aria-expanded={outputExpanded}
            onClick={onToggleOutput}
          >
            {outputExpanded ? "Hide output" : "Output"}
          </button>
        )}
        <OverflowMenu
          label={`Actions for ${title} from ${date.toLocaleDateString()}`}
          items={[
            { label: "Run again", onSelect: onRerun, disabled: actionsBusy },
            { label: "Delete", onSelect: onDelete, disabled: actionsBusy, danger: true },
          ]}
        />
      </header>
      <div className="divide-y divide-slate-200/80 border-t border-slate-200/80 dark:divide-slate-800 dark:border-slate-800">
        {group.runs.map((run) => (
          <RunMethodRow
            key={run.id}
            run={run}
            legacy={group.kind === "legacy"}
            selected={selectedPolicyId === run.id}
            onSelect={() => onSelectPolicy(run.id)}
          />
        ))}
      </div>
      {task && outputExpanded && <TaskOutputPanel task={task} context={title} />}
    </article>
    </Tooltip>
  );
}

function PendingRunCard({
  task,
  expanded,
  onToggleOutput,
}: {
  task: TaskStatus;
  expanded: boolean;
  onToggleOutput: () => void;
}) {
  const progress = task.total > 0 ? `${task.completed}/${task.total}` : "Starting";
  return (
    <article className="overflow-hidden" data-task-id={task.task_id}>
      <div className="flex items-center gap-3 border-l-2 border-teal-500 bg-teal-50/50 px-4 py-3 dark:bg-teal-950/20">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${task.status === "failed" ? "bg-red-500" : task.status === "cancelled" ? "bg-slate-400" : "bg-teal-500"}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{task.title ?? "Analysis run"}</h3>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {titleCase(task.status)} · {progress}
          </p>
          {task.error && <p className="mt-1 line-clamp-2 text-xs text-red-600 dark:text-red-400">{task.error}</p>}
        </div>
        {(task.has_output || task.status === "running" || task.status === "cancelling" || task.status === "failed") && (
          <button type="button" className="btn-secondary min-h-8 shrink-0 px-2.5 py-1 text-xs" aria-expanded={expanded} onClick={onToggleOutput}>
            {expanded ? "Hide output" : "Output"}
          </button>
        )}
      </div>
      {expanded && <TaskOutputPanel task={task} context={task.provider_name ?? task.title ?? "Analysis run"} />}
    </article>
  );
}

// ── Provider page ─────────────────────────────────────────────────────────────

export function PolicyList({ provider, selectedPolicyId, onSelectPolicy, historyTargetTaskId, historyTargetNonce }: Props) {
  const qc = useQueryClient();
  const { tasks } = useTasks();
  const taskCanAffectSelectedProvider = tasks.some((task) =>
    task.status === "running" || task.status === "cancelling"
      ? task.provider_id === provider?.id || ["collection-analysis", "refresh", "score-all"].includes(task.kind ?? "")
      : false,
  );
  const { data: runs = [], isLoading } = useRuns(provider?.id ?? null, taskCanAffectSelectedProvider);
  const { data: schedules = [] } = useSchedules(provider?.id ?? null);
  const actions = useRunActions(provider?.id ?? "");
  const schedule = schedules[0] ?? null;

  const [sourceUrl, setSourceUrl] = useState("");
  const [savedSourceUrl, setSavedSourceUrl] = useState("");
  const [sourceLookupMessage, setSourceLookupMessage] = useState("");
  const [editingSource, setEditingSource] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RunGroup | null>(null);
  const [rerunFallback, setRerunFallback] = useState<RunGroup | null>(null);
  const [checkingRunId, setCheckingRunId] = useState<string | null>(null);
  const [historyActionError, setHistoryActionError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const newAnalysisRef = useRef<HTMLDivElement>(null);

  // Keep the source input in sync when switching providers.
  useEffect(() => {
    const nextSourceUrl = provider?.source_url ?? "";
    setSourceUrl(nextSourceUrl);
    setSavedSourceUrl(nextSourceUrl);
    setSourceLookupMessage("");
    setEditingSource(false);
  }, [provider?.id, provider?.source_url]);

  useEffect(() => {
    if (!historyTargetTaskId || !provider) return;
    setExpandedTaskId(historyTargetTaskId);
    requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(`[data-task-id="${historyTargetTaskId}"]`);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
      target?.querySelector<HTMLElement>("button[aria-expanded]")?.focus();
    });
  }, [historyTargetTaskId, historyTargetNonce, provider]);

  const taskLifecycleSignature = useMemo(
    () => tasks.map((task) => `${task.task_id}:${task.status}:${task.completed}:${task.failed}`).join("|"),
    [tasks],
  );

  useEffect(() => {
    if (!provider) return;
    qc.invalidateQueries({ queryKey: ["runs", provider.id] });
    qc.invalidateQueries({ queryKey: ["providers"] });
  }, [provider?.id, taskLifecycleSignature, qc]);

  if (!provider) {
    return (
      <div className="flex flex-1 items-center justify-center text-slate-400 dark:text-slate-500">
        <div className="text-center">
          <p className="font-medium text-slate-500 dark:text-slate-400">Select a company</p>
          <p className="mt-1 text-sm">Configure its policy source and review past analyses.</p>
        </div>
      </div>
    );
  }

  const scheduleOn = schedule?.enabled ?? false;
  const busy = actions.runNow.isPending || actions.upload.isPending;
  const normalizedSourceUrl = sourceUrl.trim();
  const sourceHasUnsavedChanges = normalizedSourceUrl !== savedSourceUrl;
  const showSourceEditor = !savedSourceUrl || editingSource;
  const providerTasks = tasks.filter((task) => task.provider_id === provider.id && isRunTask(task));
  const linkedTaskIds = new Set(runs.flatMap((group) => {
    const task = group.task ?? providerTasks.find((candidate) => candidate.run_id === group.run_id);
    return task ? [task.task_id] : [];
  }));
  const provisionalTasks = providerTasks.filter((task) => !linkedTaskIds.has(task.task_id));

  const handleRerun = async (group: RunGroup) => {
    setCheckingRunId(group.run_id);
    setHistoryActionError("");
    try {
      const availability = await api.getRerunAvailability(provider.id, group.run_id);
      if (!availability.available) {
        setRerunFallback(group);
        return;
      }
      actions.rerun.mutate(group.run_id, {
        onError: (error) => setHistoryActionError(error instanceof Error ? error.message : "Could not start the re-run."),
      });
    } catch (error) {
      setHistoryActionError(error instanceof Error ? error.message : "Could not check the saved source.");
    } finally {
      setCheckingRunId(null);
    }
  };

  return (
    <div className="min-w-0 flex-1 overflow-auto px-6 py-8 lg:px-8">
      {/* Provider heading */}
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">{provider.name}</h1>
        <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
          {provider.industry ?? "Uncategorized"} · {provider.policy_count} policy records
        </p>
      </div>

      {/* Research configuration */}
      <section className="surface-card mt-7 overflow-hidden">
        <div className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Website source</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
              The public privacy-policy page used for website analyses and automatic monitoring.
            </p>
          </div>
          {schedule?.needs_attention && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">Needs confirmation</span>}
        </div>
        {savedSourceUrl && !editingSource && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50/70 px-3 py-3 dark:border-slate-800 dark:bg-slate-950/40">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-2 py-1 text-[11px] font-semibold ${SOURCE_STATUS_STYLE[provider.source_status] ?? SOURCE_STATUS_STYLE.unchecked}`}>
                  {SOURCE_STATUS_LABEL[provider.source_status] ?? "Not checked"}
                  {provider.source_http_status ? ` · HTTP ${provider.source_http_status}` : ""}
                </span>
                <span className="max-w-full truncate text-xs font-medium text-slate-700 dark:text-slate-200">{savedSourceUrl}</span>
              </div>
              {provider.source_checked_at && (
                <p className="mt-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  Checked {new Date(provider.source_checked_at).toLocaleString()}
                  {provider.source_final_url && provider.source_final_url !== provider.source_url ? " · Redirect detected" : ""}
                </p>
              )}
            </div>
            <button
              type="button"
              className="text-xs font-semibold text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-400"
              disabled={actions.verifySource.isPending}
              onClick={() => actions.verifySource.mutate()}
            >
              {actions.verifySource.isPending ? "Checking…" : "Check"}
            </button>
            <button type="button" className="btn-secondary min-h-8 px-2.5 py-1 text-xs" onClick={() => setEditingSource(true)}>Edit</button>
          </div>
        )}
        {showSourceEditor && (
          <div className="mt-4">
            <label className="form-label" htmlFor="policy-source-url">Privacy policy URL</label>
            <div className="flex items-start gap-2">
              <input
                id="policy-source-url"
                className="form-input flex-1"
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://example.com/privacy"
              />
              <button
                className="btn-secondary"
                disabled={actions.setSource.isPending || !normalizedSourceUrl || !sourceHasUnsavedChanges}
                onClick={() => actions.setSource.mutate(normalizedSourceUrl, {
                  onSuccess: (updatedProvider) => {
                    const updatedSourceUrl = updatedProvider.source_url ?? "";
                    setSavedSourceUrl(updatedSourceUrl);
                    setSourceUrl(updatedSourceUrl);
                    setEditingSource(false);
                  },
                })}
              >
                {actions.setSource.isPending ? "Saving…" : "Save"}
              </button>
              {savedSourceUrl && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setSourceUrl(savedSourceUrl);
                    setEditingSource(false);
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
            {sourceHasUnsavedChanges && <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">Save this URL before starting a website analysis.</p>}
          </div>
        )}
        {!savedSourceUrl && !sourceHasUnsavedChanges && (
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
            <button
              className="text-xs font-semibold text-teal-700 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-teal-400"
              disabled={actions.previewSource.isPending || !provider.domain}
              onClick={() => actions.previewSource.mutate(undefined, {
                onSuccess: (preview) => {
                  if (preview.url) {
                    setSourceUrl(preview.url);
                    setSourceLookupMessage(
                      preview.strategy === "ota"
                        ? "Suggested from Open Terms Archive. Review and save it to confirm."
                        : `Suggested from ${preview.notes || "the company website"}. Review and save it to confirm.`,
                    );
                  } else {
                    setSourceLookupMessage("No privacy-policy source was found automatically. Enter one above if you know it.");
                  }
                },
                onError: () => setSourceLookupMessage("Source discovery is temporarily unavailable. Enter a policy URL above if you know it."),
              })}
            >
              {actions.previewSource.isPending ? "Looking for a privacy policy…" : "Find a privacy policy automatically"}
            </button>
            {!provider.domain && <span className="text-xs text-slate-400">Add a company website before using discovery.</span>}
          </div>
        )}
        {sourceLookupMessage && <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">{sourceLookupMessage}</p>}
        </div>

      {/* Explicit analysis actions */}
      <div ref={newAnalysisRef} tabIndex={-1} className="border-t border-slate-300 p-5 focus-visible:outline-none dark:border-slate-800">
        <div>
          <h2 className="text-sm font-semibold">Start a new analysis</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
            Choose where the policy should come from. Results will appear in the history below.
          </p>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <button
            className="group rounded-md border border-teal-300 bg-teal-50/50 p-4 text-left transition-colors hover:border-teal-600 hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-teal-900 dark:bg-teal-950/25 dark:hover:border-teal-700 dark:hover:bg-teal-950/40"
            disabled={busy || !savedSourceUrl || sourceHasUnsavedChanges}
            onClick={() => actions.runNow.mutate()}
          >
            <span className="block text-sm font-semibold text-teal-800 dark:text-teal-300">
              {actions.runNow.isPending ? "Starting…" : "Analyze website"}
            </span>
            <span className="mt-1 block text-xs leading-5 text-teal-700/80 dark:text-teal-400">
              Crawl the saved page and generate policy results.
            </span>
          </button>
          <button
            className="rounded-md border border-slate-300 p-4 text-left transition-colors hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-800/60"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <span className="block text-sm font-semibold">
              {actions.upload.isPending ? "Uploading…" : "Upload and analyze a PDF"}
            </span>
            <span className="mt-1 block text-xs leading-5 text-slate-500 dark:text-slate-400">
              Use a policy document from your computer instead.
            </span>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) actions.upload.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {/* Automatic monitoring */}
      <div className="border-t border-slate-300 p-5 dark:border-slate-800">
        <div className="flex items-start gap-3">
          <Toggle
            on={scheduleOn}
            disabled={actions.toggle.isPending || !savedSourceUrl}
            onChange={(v) => actions.toggle.mutate({ enabled: v })}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold">Monitor for policy changes</h2>
              {scheduleOn && schedule && (
                <select
                  aria-label="Monitoring frequency"
                  className="form-input w-28 py-1 text-xs"
                  value={schedule.cadence}
                  onChange={(e) => actions.toggle.mutate({ enabled: true, cadence: e.target.value })}
                >
                  {CADENCES.map((c) => (
                    <option key={c} value={c}>{titleCase(c)}</option>
                  ))}
                </select>
              )}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
              {savedSourceUrl
                ? "Check the saved website source automatically and analyze it when the policy changes."
                : "Save a website source before enabling automatic monitoring."}
            </p>
            {scheduleOn && schedule && (
              <p className="mt-2 text-xs text-slate-400">
                {schedule.last_status !== "idle" ? `${titleCase(schedule.last_status)} · ` : ""}
                Next check {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "not scheduled"}
              </p>
            )}
          </div>
        </div>
      </div>
      </section>

      {/* Analysis history */}
      <section className="mt-8">
        <div className="mb-3">
          <h2 className="text-sm font-semibold">Analysis history</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Select a method to inspect its results.
          </p>
          {historyActionError && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{historyActionError}</p>}
        </div>
        {isLoading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : runs.length === 0 && provisionalTasks.length === 0 ? (
          <p className="text-sm text-slate-400">
            No analyses yet. Analyze the saved website or upload a PDF to get started.
          </p>
        ) : (
          <div className="surface-card divide-y divide-slate-300 overflow-hidden dark:divide-slate-700">
            {provisionalTasks.map((task) => (
              <PendingRunCard
                key={task.task_id}
                task={task}
                expanded={expandedTaskId === task.task_id}
                onToggleOutput={() => setExpandedTaskId((current) => current === task.task_id ? null : task.task_id)}
              />
            ))}
            {runs.map((group) => (
              <RunCard
                key={group.run_group ?? group.runs[0].id}
                group={group}
                task={group.task ?? providerTasks.find((task) => task.run_id === group.run_id) ?? null}
                outputExpanded={expandedTaskId === (group.task ?? providerTasks.find((task) => task.run_id === group.run_id))?.task_id}
                onToggleOutput={() => {
                  const task = group.task ?? providerTasks.find((candidate) => candidate.run_id === group.run_id);
                  if (task) setExpandedTaskId((current) => current === task.task_id ? null : task.task_id);
                }}
                onRerun={() => handleRerun(group)}
                onDelete={() => setDeleteTarget(group)}
                actionsBusy={checkingRunId === group.run_id || actions.rerun.isPending || actions.deleteRun.isPending}
                selectedPolicyId={selectedPolicyId}
                onSelectPolicy={onSelectPolicy}
              />
            ))}
          </div>
        )}
      </section>

      {deleteTarget && (
        <Modal title="Delete analysis run" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            Delete this analysis run? Its results and saved output will be permanently removed.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button
              type="button"
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              disabled={actions.deleteRun.isPending}
              onClick={() => actions.deleteRun.mutate(deleteTarget.run_id, {
                onSuccess: () => {
                  if (deleteTarget.runs.some((run) => run.id === selectedPolicyId)) onSelectPolicy(null);
                  setDeleteTarget(null);
                },
                onError: (error) => setHistoryActionError(error instanceof Error ? error.message : "Could not delete the run."),
              })}
            >
              {actions.deleteRun.isPending ? "Deleting…" : "Delete"}
            </button>
          </div>
        </Modal>
      )}

      {rerunFallback && (
        <Modal title="Saved source unavailable" onClose={() => setRerunFallback(null)}>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            The saved copy for this run isn’t available. Start a new analysis for {provider.name} instead?
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setRerunFallback(null)}>Cancel</button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setRerunFallback(null);
                requestAnimationFrame(() => {
                  newAnalysisRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                  newAnalysisRef.current?.focus();
                });
              }}
            >
              Start new analysis
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
