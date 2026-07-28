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
import { SelectMenu } from "./SelectMenu";
import { Tooltip } from "./Tooltip";
import { CompanyLogo } from "./CompanyLogo";
import { materialSelected, materialValue, MdFilledButton, MdOutlinedButton, MdOutlinedTextField, MdSwitch, MdTextButton } from "./MaterialControls";

interface Props {
  provider: Provider | null;
  selectedPolicyId: string | null;
  onSelectPolicy: (policy: Policy | null) => void;
  historyTargetTaskId?: string | null;
  historyTargetNonce?: number;
}

const CADENCES = ["daily", "weekly", "monthly"];

const STATUS_STYLES: Record<string, string> = {
  succeeded: "m3-status-success",
  done: "m3-status-success",
  running: "m3-status-primary",
  cancelling: "m3-status-warning",
  cancelled: "m3-status-neutral",
  failed: "m3-status-error",
  pending: "m3-status-warning",
};

const METHOD_LABEL: Record<string, string> = {
  website: "Live policy page",
  pdf_from_page: "Policy page PDF",
  pdf_upload: "Uploaded policy PDF",
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
  unchecked: "m3-source-status m3-source-status-neutral",
  available: "m3-source-status m3-source-status-ready",
  restricted: "m3-source-status m3-source-status-warning",
  broken: "m3-source-status m3-source-status-error",
  error: "m3-source-status m3-source-status-error",
  missing: "m3-source-status m3-source-status-neutral",
};

function companyHealth(provider: Provider): { label: string; tone: "ready" | "attention" | "error" | "neutral" } {
  const allFailed = provider.policy_count > 0 && provider.failed_count === provider.policy_count;
  const mixedResults = provider.failed_count > 0 && provider.succeeded_count > 0;
  if (["broken", "error"].includes(provider.source_status) || allFailed) return { label: "Needs attention", tone: "error" };
  if (provider.source_status === "restricted" || mixedResults || provider.failed_count > 0) return { label: "Attention recommended", tone: "attention" };
  if (provider.source_status === "available") return { label: "Ready", tone: "ready" };
  return { label: "Not ready", tone: "neutral" };
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function isValidWebUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function Toggle({ label, on, onChange, disabled }: { label: string; on: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <MdSwitch
      aria-label={label}
      selected={on}
      disabled={disabled}
      icons
      onChange={(event) => onChange(materialSelected(event))}
    />
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
    : METHOD_LABEL[run.method] ?? "Imported analysis method";
  return (
    <button
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      aria-label={`Open ${methodLabel.toLowerCase()} results`}
      className={`m3-run-method group flex min-h-14 w-full items-center px-3 py-2.5 text-left text-sm sm:px-4 ${
        selected
          ? "m3-run-method-selected"
          : ""
      }`}
    >
      <span className="min-w-0 truncate font-semibold">{methodLabel}</span>
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
  onSelectPolicy: (policy: Policy) => void;
}) {
  const date = new Date(group.created_at);
  const title = group.kind === "legacy"
    ? "Archived analysis"
    : group.kind === "upload"
      ? "Uploaded policy PDF"
      : "Live policy page";
  const status = groupStatus(group, task);
  const rerun = group.runs.some((run) => run.rerun_of_policy_id);
  const captureText = group.capture_date
    ? new Date(`${group.capture_date}T00:00:00`).toLocaleDateString()
    : "Unknown";
  const canShowOutput = !!task && (task.has_output || ["running", "cancelling", "failed"].includes(task.status));
  const tooltipContent = (
    <>
      <div className="font-semibold text-white">{group.scheduled ? "Automatic" : "Manual"} {title.toLowerCase()}</div>
      <div className="mt-1 text-[var(--md-sys-color-on-surface-variant)]">{group.runs.length} {group.runs.length === 1 ? "method" : "methods"} · Started {date.toLocaleString()}</div>
      <div className="text-[var(--md-sys-color-on-surface-variant)]">Source captured {captureText}</div>
      <div className="mt-1 font-mono text-[var(--md-sys-color-on-surface-variant)]">Run {group.run_id.slice(0, 8)}</div>
    </>
  );

  return (
    <Tooltip content={tooltipContent} side="bottom" align="end">
    <article
      className="m3-run-group group/run relative overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--md-sys-color-primary)]"
      data-task-id={task?.task_id}
      role="group"
      aria-label={`${title} from ${date.toLocaleDateString()}`}
      tabIndex={0}
    >
      <header className="m3-run-group-header flex items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--md-sys-color-on-surface)]">{title}</h3>
            {rerun && <span className="m3-run-rerun">Re-run</span>}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[status] ?? ""}`}>{titleCase(status)}</span>
          </div>
          <p className="mt-0.5 text-xs text-[var(--md-sys-color-on-surface-variant)]">
            {group.scheduled ? "Automatic" : "Manual"} · <time dateTime={date.toISOString()}>{date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time>
            {task && task.total > 0 && ["running", "cancelling"].includes(task.status) ? ` · ${task.completed}/${task.total}` : ""}
          </p>
        </div>
        {canShowOutput && (
          <MdOutlinedButton
            className="min-h-8 shrink-0 text-xs"
            aria-expanded={outputExpanded}
            onClick={onToggleOutput}
          >{outputExpanded ? "Hide output" : "Output"}</MdOutlinedButton>
        )}
        <OverflowMenu
          label={`Actions for ${title} from ${date.toLocaleDateString()}`}
          items={[
            { label: "Run again", onSelect: onRerun, disabled: actionsBusy },
            { label: "Delete", onSelect: onDelete, disabled: actionsBusy, danger: true },
          ]}
        />
      </header>
      <div className="m3-run-methods">
        {group.runs.map((run) => (
          <RunMethodRow
            key={run.id}
            run={run}
            legacy={group.kind === "legacy"}
            selected={selectedPolicyId === run.id}
            onSelect={() => onSelectPolicy(run)}
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
    <article className="m3-run-group overflow-hidden" data-task-id={task.task_id}>
      <div className="m3-run-group-header flex items-center gap-3 px-4 py-3">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${task.status === "failed" ? "bg-[var(--md-sys-color-error)]" : task.status === "cancelled" ? "bg-[var(--md-sys-color-on-surface-variant)]" : "bg-[var(--md-sys-color-primary)]"}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{task.title ?? "Analysis run"}</h3>
          <p className="mt-0.5 text-xs text-[var(--md-sys-color-on-surface-variant)]">
            {titleCase(task.status)} · {progress}
          </p>
          {task.error && <p className="mt-1 line-clamp-2 text-xs text-[var(--md-sys-color-error)]">{task.error}</p>}
        </div>
        {(task.has_output || task.status === "running" || task.status === "cancelling" || task.status === "failed") && (
          <MdOutlinedButton className="min-h-8 shrink-0 text-xs" aria-expanded={expanded} onClick={onToggleOutput}>{expanded ? "Hide output" : "Output"}</MdOutlinedButton>
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
  const { data: runs = [], isLoading, isError, error } = useRuns(provider?.id ?? null, taskCanAffectSelectedProvider);
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
  const newAnalysisRef = useRef<HTMLElement>(null);

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
      <div className="flex flex-1 items-center justify-center p-6 text-[var(--md-sys-color-on-surface-variant)]">
        <div className="m3-empty-state text-center">
          <p className="font-display text-2xl font-semibold text-[var(--md-sys-color-on-surface)]">Select a company</p>
          <p className="mt-2 text-sm leading-6">Configure its policy source and review past analyses.</p>
        </div>
      </div>
    );
  }

  const scheduleOn = schedule?.enabled ?? false;
  const busy = actions.runNow.isPending || actions.upload.isPending;
  const workspaceActionError = actions.setSource.error
    ?? actions.verifySource.error
    ?? actions.previewSource.error
    ?? actions.runNow.error
    ?? actions.upload.error
    ?? actions.toggle.error;
  const normalizedSourceUrl = sourceUrl.trim();
  const sourceUrlIsValid = isValidWebUrl(normalizedSourceUrl);
  const sourceHasUnsavedChanges = normalizedSourceUrl !== savedSourceUrl;
  const providerTasks = tasks.filter((task) => task.provider_id === provider.id && isRunTask(task));
  const linkedTaskIds = new Set(runs.flatMap((group) => {
    const task = group.task ?? providerTasks.find((candidate) => candidate.run_id === group.run_id);
    return task ? [task.task_id] : [];
  }));
  const provisionalTasks = providerTasks.filter((task) => !linkedTaskIds.has(task.task_id));
  const health = companyHealth(provider);

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
    <div className="m3-company-record min-w-0 flex-1 overflow-auto px-4 py-3 sm:px-5 lg:px-6">
      <div className="mx-auto w-full max-w-5xl">
      {/* Provider heading */}
      <header className="overflow-hidden py-2">
        <div className="flex items-center gap-3 sm:gap-4">
          <CompanyLogo name={provider.name} domain={provider.domain} className="h-11 w-11 sm:h-12 sm:w-12" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`m3-company-health m3-company-health-${health.tone}`}><span aria-hidden="true" />{health.label}</span>
            </div>
            <h1 className="mt-0.5 truncate font-display text-3xl font-normal tracking-normal text-[var(--md-sys-color-on-surface)] sm:text-4xl sm:leading-tight">{provider.name}</h1>
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-4">
          <div><dt className="section-kicker">Industry</dt><dd className="mt-1 truncate text-sm font-semibold text-[var(--md-sys-color-on-surface)]">{provider.industry ?? "Uncategorized"}</dd></div>
          <div><dt className="section-kicker">Ticker</dt><dd className="data-value mt-1 text-sm font-semibold text-[var(--md-sys-color-on-surface)]">{provider.tickers.join(", ") || "—"}</dd></div>
          <div><dt className="section-kicker">Analyses</dt><dd className="data-value mt-1 text-sm font-semibold text-[var(--md-sys-color-on-surface)]">{provider.policy_count}</dd></div>
          <div><dt className="section-kicker">Policy source</dt><dd className="mt-1 text-sm font-semibold text-[var(--md-sys-color-on-surface)]">{SOURCE_STATUS_LABEL[provider.source_status] ?? "Not checked"}</dd></div>
        </dl>
      </header>

      {/* Research configuration */}
      <section className="isolate mt-4 overflow-visible">
        {workspaceActionError && (
          <p role="alert" className="m-3 mb-0 sm:m-5 sm:mb-0 status-error">
            {workspaceActionError instanceof Error ? workspaceActionError.message : "The action could not be completed. Try again."}
          </p>
        )}
      <section ref={newAnalysisRef} tabIndex={-1} aria-labelledby="new-analysis-heading" className="py-2 focus-visible:outline-none sm:py-3">
        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end sm:gap-5">
          <div>
            <h2 id="new-analysis-heading" className="mt-1 font-display text-2xl font-normal">Start an analysis</h2>
            <p className="mt-1 text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
              Choose the saved website or a policy PDF.
            </p>
          </div>
        </div>
        <div className="mt-4 grid items-stretch gap-3 md:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]">
          <article className="research-panel m3-analysis-choice m3-analysis-choice-recommended flex min-w-0 flex-col rounded-[var(--md-sys-shape-corner-large)] p-3 sm:p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="m3-recommended-label">Recommended</p>
                <h3 className="text-lg font-medium text-[var(--md-sys-color-on-surface)]">Website analysis</h3>
                <p className="mt-1 text-sm leading-5 text-[var(--md-sys-color-on-surface-variant)]">Analyze the privacy policy at the saved URL.</p>
              </div>
              {schedule?.needs_attention && <span className="text-xs font-semibold text-[var(--md-sys-color-tertiary)]">Source needs confirmation</span>}
            </div>
            <div className="mt-4 flex-1">
              <p className="m3-source-field-label">Privacy policy source</p>
              {savedSourceUrl && !editingSource ? (
                <div className="m3-source-summary mt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-xs font-semibold ${SOURCE_STATUS_STYLE[provider.source_status] ?? SOURCE_STATUS_STYLE.unchecked}`}>
                      {SOURCE_STATUS_LABEL[provider.source_status] ?? "Not checked"}{provider.source_http_status ? ` · HTTP ${provider.source_http_status}` : ""}
                    </span>
                  </div>
                  <p className="m3-source-url mt-2 break-all">{savedSourceUrl}</p>
                  {provider.source_checked_at && <p className="mt-1 data-value text-[11px] text-[var(--md-sys-color-on-surface-variant)]">Last checked {new Date(provider.source_checked_at).toLocaleString()}</p>}
                  <div className="mt-1 flex flex-wrap gap-1">
                    <MdTextButton className="m3-source-action" disabled={actions.verifySource.isPending} onClick={() => actions.verifySource.mutate()}>{actions.verifySource.isPending ? "Checking…" : "Check source"}</MdTextButton>
                    <MdTextButton className="m3-source-action" onClick={() => setEditingSource(true)}>Change source</MdTextButton>
                  </div>
                </div>
              ) : (
                <div className="mt-2">
                  <MdOutlinedTextField
                    id="policy-source-url"
                    type="url"
                    className="w-full"
                    label="Privacy policy URL"
                    value={sourceUrl}
                    onInput={(event) => setSourceUrl(materialValue(event))}
                    placeholder="https://example.com/privacy"
                    error={Boolean(normalizedSourceUrl && !sourceUrlIsValid)}
                    errorText="Enter a complete address beginning with http:// or https://."
                    aria-describedby="policy-source-url-help"
                  />
                  <div id="policy-source-url-help">
                    {normalizedSourceUrl && !sourceUrlIsValid ? <p className="mt-2 text-xs text-[var(--md-sys-color-error)]">Enter a complete address beginning with http:// or https://.</p> : sourceHasUnsavedChanges ? <p className="mt-2 text-xs text-[var(--md-sys-color-tertiary)]">Save this address before starting an analysis.</p> : null}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <MdOutlinedButton disabled={actions.setSource.isPending || !sourceUrlIsValid || !sourceHasUnsavedChanges} onClick={() => actions.setSource.mutate(normalizedSourceUrl, { onSuccess: (updatedProvider) => { const url = updatedProvider.source_url ?? ""; setSavedSourceUrl(url); setSourceUrl(url); setEditingSource(false); } })}>{actions.setSource.isPending ? "Saving…" : "Save source"}</MdOutlinedButton>
                    {savedSourceUrl && <MdOutlinedButton onClick={() => { setSourceUrl(savedSourceUrl); setEditingSource(false); }}>Cancel</MdOutlinedButton>}
                    {!savedSourceUrl && !sourceHasUnsavedChanges && <MdTextButton disabled={actions.previewSource.isPending || !provider.domain} onClick={() => actions.previewSource.mutate(undefined, { onSuccess: (preview) => { if (preview.url) { setSourceUrl(preview.url); setSourceLookupMessage("Suggested source found. Review and save it to confirm."); } else setSourceLookupMessage("No source was found automatically. Enter one if you know it."); }, onError: () => setSourceLookupMessage("Source discovery is temporarily unavailable.") })}>{actions.previewSource.isPending ? "Searching…" : "Find automatically"}</MdTextButton>}
                  </div>
                  {sourceLookupMessage && <p className="mt-2 text-xs leading-5 text-[var(--md-sys-color-on-surface-variant)]">{sourceLookupMessage}</p>}
                </div>
              )}
            </div>
            {(!savedSourceUrl || sourceHasUnsavedChanges) && <p id="website-analysis-status" className="mt-3 text-xs leading-5 text-[var(--md-sys-color-tertiary)]">{!savedSourceUrl ? "Add and save a privacy policy URL to continue." : "Save the URL changes to continue."}</p>}
            <MdFilledButton className="mt-3 w-full" disabled={busy || !savedSourceUrl || sourceHasUnsavedChanges} aria-describedby={!savedSourceUrl || sourceHasUnsavedChanges ? "website-analysis-status" : undefined} onClick={() => actions.runNow.mutate()}>
              {actions.runNow.isPending ? "Starting analysis…" : "Analyze website"}
            </MdFilledButton>
          </article>
          <article className="ui-subtle m3-analysis-choice flex flex-col rounded-[var(--md-sys-shape-corner-large)] p-3 sm:p-4">
            <h3 className="text-lg font-medium text-[var(--md-sys-color-on-surface)]">PDF analysis</h3>
            <p className="mt-2 flex-1 text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">Upload a specific policy edition when the website is unavailable or has changed.</p>
            <MdOutlinedButton
            className="mt-4 w-full"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
              {actions.upload.isPending ? "Uploading PDF…" : "Choose PDF"}
          </MdOutlinedButton>
          </article>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            aria-label="Upload policy PDF"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) actions.upload.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      </section>

      {/* Automatic monitoring */}
      <div className="ui-subtle mb-4 rounded-[var(--md-sys-shape-corner-large)] p-4 sm:mb-5">
        <div className="flex items-start gap-2 sm:gap-3">
          <Toggle
            label="Monitor for policy changes"
            on={scheduleOn}
            disabled={actions.toggle.isPending || !savedSourceUrl}
            onChange={(v) => actions.toggle.mutate({ enabled: v })}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold">Monitor for policy changes</h2>
              {scheduleOn && schedule && (
                <SelectMenu
                  label="Monitoring frequency"
                  heading="Frequency"
                  className="w-28"
                  value={schedule.cadence}
                  options={CADENCES.map((cadence) => ({ value: cadence, label: titleCase(cadence) }))}
                  onChange={(cadence) => actions.toggle.mutate({ enabled: true, cadence })}
                />
              )}
            </div>
            <p className="mt-1 text-xs leading-5 text-[var(--md-sys-color-on-surface-variant)]">
              {savedSourceUrl
                ? "Check the saved website source automatically and analyze it when the policy changes."
                : "Save a website source before enabling automatic monitoring."}
            </p>
            {scheduleOn && schedule && (
              <p className="mt-2 text-xs text-[var(--md-sys-color-on-surface-variant)]">
                {schedule.last_status !== "idle" ? `${titleCase(schedule.last_status)} · ` : ""}
                Next check {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "not scheduled"}
              </p>
            )}
          </div>
        </div>
      </div>
      </section>

      {/* Analysis history */}
      <section className="mt-5">
        <div className="mb-3">
          <h2 className="font-display text-2xl font-semibold">Analysis history</h2>
          <p className="mt-1 text-xs text-[var(--md-sys-color-on-surface-variant)]">
            Review completed and in-progress analyses.
          </p>
          {historyActionError && <p role="alert" className="mt-2 status-error">{historyActionError}</p>}
        </div>
        {isLoading ? (
          <p role="status" className="quiet-state py-6">Loading analysis history…</p>
        ) : isError ? (
          <p role="alert" className="status-error">Could not load analysis history. {error instanceof Error ? error.message : "Try refreshing the page."}</p>
        ) : runs.length === 0 && provisionalTasks.length === 0 ? (
          <p className="quiet-state py-6">
            No analyses yet. Analyze the website or upload a PDF to get started.
          </p>
        ) : (
          <div className="m3-analysis-history">
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
          <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
            Delete this analysis run? Its results and saved output will be permanently removed.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <MdOutlinedButton onClick={() => setDeleteTarget(null)}>Cancel</MdOutlinedButton>
            <MdFilledButton
              className="material-error"
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
            </MdFilledButton>
          </div>
        </Modal>
      )}

      {rerunFallback && (
        <Modal title="Saved source unavailable" onClose={() => setRerunFallback(null)}>
          <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
            The saved copy for this run isn’t available. Start a new analysis for {provider.name} instead?
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <MdOutlinedButton onClick={() => setRerunFallback(null)}>Cancel</MdOutlinedButton>
            <MdFilledButton
              onClick={() => {
                setRerunFallback(null);
                requestAnimationFrame(() => {
                  newAnalysisRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                  newAnalysisRef.current?.focus();
                });
              }}
            >
              Start new analysis
            </MdFilledButton>
          </div>
        </Modal>
      )}
      </div>
    </div>
  );
}
