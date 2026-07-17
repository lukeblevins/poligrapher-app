import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { Provider, Schedule } from "../../api/types";
import { useScheduleMutations, useSchedules } from "../../hooks/useSchedules";
import { Modal } from "../Modal";
import { SelectMenu } from "../SelectMenu";

const CADENCES = ["daily", "weekly", "monthly"];

function fmt(dt: string | null): string {
  if (!dt) return "—";
  return new Date(dt).toLocaleString();
}

function ConfidenceBadge({ confidence, auto }: { confidence: number; auto: boolean }) {
  const cls = auto
    ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400"
    : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${cls}`}>
      {(confidence * 100).toFixed(0)}% {auto ? "auto" : "needs confirm"}
    </span>
  );
}

function ExistingSchedule({ schedule, providerId }: { schedule: Schedule; providerId: string }) {
  const m = useScheduleMutations(providerId);
  const [confirmUrl, setConfirmUrl] = useState(schedule.last_source_url ?? "");

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="form-label mb-0">Cadence</span>
        <SelectMenu
          label="Schedule cadence"
          heading="Cadence"
          className="w-40"
          value={schedule.cadence}
          options={CADENCES.map((cadence) => ({ value: cadence, label: cadence }))}
          onChange={(cadence) => m.update.mutate({ id: schedule.id, body: { cadence } })}
        />
        <label className="ml-2 flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={schedule.enabled}
            onChange={(e) => m.update.mutate({ id: schedule.id, body: { enabled: e.target.checked } })}
          />
          Enabled
        </label>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-slate-500">Status</dt>
        <dd>{schedule.last_status}</dd>
        <dt className="text-slate-500">Last run</dt>
        <dd>{fmt(schedule.last_run_at)}</dd>
        <dt className="text-slate-500">Next run</dt>
        <dd>{fmt(schedule.next_run_at)}</dd>
        <dt className="text-slate-500">Resolved source</dt>
        <dd className="truncate">
          {schedule.last_strategy ? (
            <>
              <span className="text-slate-500 dark:text-slate-400">{schedule.last_strategy}</span>{" "}
              {schedule.last_source_url ? (
                <a className="text-brand underline" href={schedule.last_source_url} target="_blank" rel="noreferrer">
                  {schedule.last_source_url}
                </a>
              ) : (
                "—"
              )}
            </>
          ) : (
            "— (not run yet)"
          )}
        </dd>
      </dl>

      {schedule.needs_attention && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          <p className="mb-2 font-medium text-amber-800 dark:text-amber-300">
            Source needs confirmation
          </p>
          <p className="mb-2 text-xs text-amber-700 dark:text-amber-400">
            The current policy source couldn't be resolved confidently. Confirm the correct URL and
            it will be used for all future runs.
          </p>
          <div className="flex gap-2">
            <input
              aria-label="Confirmed privacy policy URL"
              className="form-input flex-1"
              value={confirmUrl}
              onChange={(e) => setConfirmUrl(e.target.value)}
              placeholder="https://…/privacy-policy"
            />
            <button
              className="btn-primary"
              disabled={!confirmUrl.trim() || m.confirm.isPending}
              onClick={() => m.confirm.mutate({ id: schedule.id, url: confirmUrl.trim() })}
            >
              Confirm
            </button>
          </div>
        </div>
      )}

      <div className="flex justify-between pt-1">
        <button
          className="btn-secondary text-xs text-red-600 dark:text-red-400"
          onClick={() => m.remove.mutate(schedule.id)}
        >
          Delete schedule
        </button>
        <button className="btn-primary" disabled={m.run.isPending} onClick={() => m.run.mutate(schedule.id)}>
          {m.run.isPending ? "Starting…" : "Run now"}
        </button>
      </div>
    </div>
  );
}

function CreateSchedule({ provider }: { provider: Provider }) {
  const m = useScheduleMutations(provider.id);
  const [cadence, setCadence] = useState("weekly");
  const [checkSource, setCheckSource] = useState(false);

  const preview = useQuery({
    queryKey: ["source-preview", provider.id],
    queryFn: () => api.sourcePreview(provider.id),
    enabled: checkSource,
    retry: false,
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No schedule yet. A schedule re-acquires this provider's privacy policy on a cadence and
        re-runs generation + scoring only when the policy actually changes.
      </p>

      <div>
        <button className="btn-secondary" disabled={preview.isFetching} onClick={() => setCheckSource(true)}>
          {preview.isFetching ? "Resolving source…" : "Preview current source"}
        </button>
        {preview.data && (
          <div className="mt-2 rounded-md border border-slate-200 p-3 text-sm dark:border-slate-700">
            {preview.data.resolved ? (
              <>
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-slate-500 dark:text-slate-400">{preview.data.strategy}</span>
                  <ConfidenceBadge confidence={preview.data.confidence} auto={preview.data.auto} />
                </div>
                <a className="break-all text-brand underline" href={preview.data.url ?? undefined} target="_blank" rel="noreferrer">
                  {preview.data.url}
                </a>
                {!preview.data.auto && (
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                    Low confidence — runs will pause for you to confirm the source.
                  </p>
                )}
              </>
            ) : (
              <p className="text-amber-700 dark:text-amber-400">
                No source could be resolved automatically ({preview.data.notes}). Runs will ask you
                to confirm a URL.
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex items-end gap-2">
        <div>
          <span className="form-label">Cadence</span>
          <SelectMenu
            label="New schedule cadence"
            heading="Cadence"
            className="w-40"
            value={cadence}
            options={CADENCES.map((option) => ({ value: option, label: option }))}
            onChange={setCadence}
          />
        </div>
        <button
          className="btn-primary"
          disabled={m.create.isPending}
          onClick={() => m.create.mutate({ cadence, enabled: true })}
        >
          {m.create.isPending ? "Creating…" : "Create schedule"}
        </button>
      </div>
    </div>
  );
}

export function ScheduleModal({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const { data: schedules = [], isLoading } = useSchedules(provider.id);

  return (
    <Modal title={`Schedule · ${provider.name}`} onClose={onClose}>
      {isLoading ? (
        <p role="status" className="text-sm text-slate-500 dark:text-slate-400">Loading schedule…</p>
      ) : schedules.length > 0 ? (
        <ExistingSchedule schedule={schedules[0]} providerId={provider.id} />
      ) : (
        <CreateSchedule provider={provider} />
      )}
    </Modal>
  );
}
