import { useEffect, useRef, useState } from "react";

import type { Policy, Provider, RunGroup } from "../api/types";
import { useSchedules } from "../hooks/useSchedules";
import { useRunActions, useRuns } from "../hooks/useRuns";

interface Props {
  provider: Provider | null;
  selectedPolicyId: string | null;
  onSelectPolicy: (id: string) => void;
}

const CADENCES = ["daily", "weekly", "monthly"];

const STATUS_STYLES: Record<string, string> = {
  succeeded: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
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
  available: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
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
      className={`group grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 border-l-2 px-4 py-3 text-left text-sm transition-colors ${
        selected
          ? "border-teal-700 bg-teal-50/80 dark:border-teal-400 dark:bg-teal-950/35"
          : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50"
      }`}
    >
      <span className="min-w-0 flex-1">
        <span className={`block font-semibold ${selected ? "text-teal-900 dark:text-teal-100" : ""}`}>
          {methodLabel}
        </span>
        <span className="mt-0.5 block text-xs font-normal leading-4 text-slate-500 dark:text-slate-400">
          {methodDescription}
        </span>
      </span>
      <span className={`self-start rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[run.pipeline_status] ?? ""}`}>
        {titleCase(run.pipeline_status)}
      </span>
      <span className="col-span-2 flex gap-5 border-t border-slate-200/80 pt-2 text-[11px] font-medium text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span>Privacy score <b className="data-value ml-1 text-xs text-slate-800 dark:text-slate-200">{score(run.privacy_score)}</b></span>
        <span>GDPR score <b className="data-value ml-1 text-xs text-slate-800 dark:text-slate-200">{score(run.gdpr_score)}</b></span>
      </span>
    </button>
  );
}

function RunCard({
  group,
  selectedPolicyId,
  onSelectPolicy,
}: {
  group: RunGroup;
  selectedPolicyId: string | null;
  onSelectPolicy: (id: string) => void;
}) {
  const date = group.capture_date
    ? new Date(`${group.capture_date}T00:00:00`)
    : new Date(group.created_at);
  const title = group.kind === "legacy"
    ? "Legacy result"
    : group.kind === "upload"
      ? "Uploaded policy analysis"
      : "Policy analysis";
  const methodCount = group.runs.length;
  const metadata = group.kind === "legacy"
    ? "Original capture details unavailable"
    : `${group.scheduled ? "Automatic" : "Manual"} run · ${methodCount} ${methodCount === 1 ? "method" : "methods"}`;

  return (
    <article className="overflow-hidden">
      <header className="flex items-start gap-4 bg-slate-50/70 px-4 py-3.5 dark:bg-slate-900/45">
        <time className="w-12 flex-none pt-0.5 text-center" dateTime={date.toISOString()}>
          <span className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            {date.toLocaleDateString(undefined, { month: "short" })}
          </span>
          <span className="data-value mt-0.5 block text-xl font-semibold leading-none text-slate-900 dark:text-slate-100">
            {date.toLocaleDateString(undefined, { day: "numeric" })}
          </span>
          <span className="data-value mt-1 block text-[10px] text-slate-400 dark:text-slate-500">
            {date.toLocaleDateString(undefined, { year: "numeric" })}
          </span>
        </time>
        <div className="min-w-0 flex-1 border-l border-slate-200 pl-4 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
            {group.kind === "legacy" && (
              <span className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                Legacy data
              </span>
            )}
          </div>
          <p className="mt-1 text-xs leading-4 text-slate-500 dark:text-slate-400">{metadata}</p>
        </div>
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
    </article>
  );
}

// ── Provider page ─────────────────────────────────────────────────────────────

export function PolicyList({ provider, selectedPolicyId, onSelectPolicy }: Props) {
  const { data: runs = [], isLoading } = useRuns(provider?.id ?? null);
  const { data: schedules = [] } = useSchedules(provider?.id ?? null);
  const actions = useRunActions(provider?.id ?? "");
  const schedule = schedules[0] ?? null;

  const [sourceUrl, setSourceUrl] = useState("");
  const [savedSourceUrl, setSavedSourceUrl] = useState("");
  const [sourceLookupMessage, setSourceLookupMessage] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // Keep the source input in sync when switching providers.
  useEffect(() => {
    const nextSourceUrl = provider?.source_url ?? "";
    setSourceUrl(nextSourceUrl);
    setSavedSourceUrl(nextSourceUrl);
    setSourceLookupMessage("");
  }, [provider?.id, provider?.source_url]);

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
          <div className="flex items-center gap-2">
            {schedule?.needs_attention && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">Needs confirmation</span>
            )}
            <span className={`rounded px-2 py-1 text-[11px] font-semibold ${SOURCE_STATUS_STYLE[provider.source_status] ?? SOURCE_STATUS_STYLE.unchecked}`}>
              {SOURCE_STATUS_LABEL[provider.source_status] ?? "Not checked"}
              {provider.source_http_status ? ` · ${provider.source_http_status}` : ""}
            </span>
            {savedSourceUrl && (
              <button
                className="text-xs font-semibold text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-400"
                disabled={actions.verifySource.isPending}
                onClick={() => actions.verifySource.mutate()}
              >
                {actions.verifySource.isPending ? "Checking…" : "Check source"}
              </button>
            )}
          </div>
        </div>
        <label className="form-label mt-4" htmlFor="policy-source-url">Privacy policy URL</label>
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
              },
            })}
          >
            {actions.setSource.isPending ? "Saving…" : "Save source"}
          </button>
        </div>
        {sourceHasUnsavedChanges && (
          <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
            Save this URL before starting a website analysis.
          </p>
        )}
        {provider.source_checked_at && (
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
            Last checked {new Date(provider.source_checked_at).toLocaleString()}
            {provider.source_final_url && provider.source_final_url !== provider.source_url ? " · Redirect detected" : ""}
          </p>
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
      <div className="border-t border-slate-300 p-5 dark:border-slate-800">
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
            Select a result to explore its graph, statistics, and assessments.
          </p>
        </div>
        {isLoading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-slate-400">
            No analyses yet. Analyze the saved website or upload a PDF to get started.
          </p>
        ) : (
          <div className="surface-card divide-y divide-slate-300 overflow-hidden dark:divide-slate-700">
            {runs.map((group) => (
              <RunCard
                key={group.run_group ?? group.runs[0].id}
                group={group}
                selectedPolicyId={selectedPolicyId}
                onSelectPolicy={onSelectPolicy}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
