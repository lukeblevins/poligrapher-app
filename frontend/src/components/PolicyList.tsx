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
  website: "Website method",
  pdf_from_page: "PDF-from-page",
  pdf_upload: "Uploaded PDF",
};

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
      className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        on ? "bg-brand" : "bg-zinc-300 dark:bg-zinc-600"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
          on ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

// ── Run row (one analysis method within a run group) ──────────────────────────

function RunMethodRow({
  run,
  selected,
  onSelect,
}: {
  run: Policy;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${
        selected ? "bg-indigo-50 dark:bg-indigo-950/50" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
      }`}
    >
      <span className="w-32 flex-shrink-0 font-medium">{METHOD_LABEL[run.method] ?? run.method}</span>
      <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLES[run.pipeline_status] ?? ""}`}>
        {run.pipeline_status}
      </span>
      <span className="ml-auto flex gap-4 text-xs text-zinc-500 dark:text-zinc-400">
        <span>Privacy <b className="text-zinc-800 dark:text-zinc-200">{score(run.privacy_score)}</b></span>
        <span>GDPR <b className="text-zinc-800 dark:text-zinc-200">{score(run.gdpr_score)}</b></span>
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
  const date = group.capture_date ?? new Date(group.created_at).toLocaleDateString();
  return (
    <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900">
      <div className="flex items-center gap-2 border-b border-zinc-100 px-3 py-2 text-xs dark:border-zinc-800">
        <span className="font-medium">
          {group.kind === "comparison" ? "Comparison run" : "Uploaded PDF"}
        </span>
        <span className="text-zinc-400">· {date}</span>
        <span
          className={`ml-auto rounded px-1.5 py-0.5 ${
            group.scheduled
              ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
              : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
          }`}
        >
          {group.scheduled ? "scheduled" : "manual"}
        </span>
      </div>
      <div className="p-1">
        {group.runs.map((run) => (
          <RunMethodRow
            key={run.id}
            run={run}
            selected={selectedPolicyId === run.id}
            onSelect={() => onSelectPolicy(run.id)}
          />
        ))}
      </div>
    </div>
  );
}

// ── Provider page ─────────────────────────────────────────────────────────────

export function PolicyList({ provider, selectedPolicyId, onSelectPolicy }: Props) {
  const { data: runs = [], isLoading } = useRuns(provider?.id ?? null);
  const { data: schedules = [] } = useSchedules(provider?.id ?? null);
  const actions = useRunActions(provider?.id ?? "");
  const schedule = schedules[0] ?? null;

  const [sourceUrl, setSourceUrl] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // Keep the source input in sync when switching providers.
  useEffect(() => {
    setSourceUrl(provider?.source_url ?? "");
  }, [provider?.id, provider?.source_url]);

  if (!provider) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400 dark:text-zinc-500">
        <p>Select a company to view its policy source and runs.</p>
      </div>
    );
  }

  const scheduleOn = schedule?.enabled ?? false;
  const busy = actions.runNow.isPending || actions.upload.isPending;

  return (
    <div className="min-w-0 flex-1 overflow-auto p-6">
      {/* Title + schedule toggle */}
      <h1 className="text-xl font-semibold">{provider.name}</h1>
      <div className="mt-2 flex items-center gap-3">
        <Toggle
          on={scheduleOn}
          disabled={actions.toggle.isPending || !provider.source_url}
          onChange={(v) => actions.toggle.mutate({ enabled: v })}
        />
        <span className="text-sm text-zinc-600 dark:text-zinc-300">Scheduled acquisition</span>
        {!provider.source_url && (
          <span className="text-xs text-zinc-400">Set a website source below to enable</span>
        )}
        {scheduleOn && schedule && (
          <>
            <select
              className="form-input w-28 py-1 text-xs"
              value={schedule.cadence}
              onChange={(e) => actions.toggle.mutate({ enabled: true, cadence: e.target.value })}
            >
              {CADENCES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <span className="text-xs text-zinc-400">
              {schedule.last_status !== "idle" ? `${schedule.last_status} · ` : ""}
              next {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "—"}
            </span>
          </>
        )}
      </div>

      {/* Policy source */}
      <section className="mt-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Policy source</h2>
          {schedule?.needs_attention && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              needs confirmation
            </span>
          )}
        </div>
        <label className="form-label">Website URL (crawled + compared against a PDF of the same page)</label>
        <div className="flex gap-2">
          <input
            className="form-input flex-1"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://example.com/privacy"
          />
          <button
            className="btn-secondary"
            disabled={actions.setSource.isPending || sourceUrl === (provider.source_url ?? "")}
            onClick={() => actions.setSource.mutate(sourceUrl.trim())}
          >
            Save
          </button>
        </div>
        <div className="mt-3 flex gap-2">
          <button
            className="btn-primary"
            disabled={busy || !sourceUrl.trim()}
            onClick={() => actions.runNow.mutate()}
          >
            {actions.runNow.isPending ? "Starting…" : "Run comparison now"}
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
            {actions.upload.isPending ? "Uploading…" : "Analyze a PDF"}
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
      </section>

      {/* Runs */}
      <section className="mt-6">
        <h2 className="mb-2 text-sm font-semibold">Runs</h2>
        {isLoading ? (
          <p className="text-sm text-zinc-400">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-zinc-400">
            No runs yet. Set a website source and run a comparison, or analyze a PDF.
          </p>
        ) : (
          <div className="space-y-3">
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
