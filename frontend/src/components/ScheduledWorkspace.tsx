import { useQueries } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { isTaskActive, type Schedule, type TaskStatus } from "../api/types";
import { useProviders } from "../hooks/queries";
import { useTasks } from "../hooks/useTasks";
import { MdFilledButton } from "./MaterialControls";
import { BulkActionsModal } from "./modals/BulkActionsModal";

function taskTitle(task: TaskStatus) {
  return task.title ?? task.label ?? task.kind ?? "Background task";
}

function taskState(task: TaskStatus) {
  if (task.status === "failed" || task.failed > 0) return "Needs attention";
  if (isTaskActive(task.status)) return "In progress";
  if (task.status === "done") return "Complete";
  return task.status;
}

function progressLabel(task: TaskStatus) {
  return task.total > 0 ? `${task.completed} of ${task.total} complete` : isTaskActive(task.status) ? "Preparing work" : "";
}

export function ScheduledWorkspace() {
  const { data: providers = [] } = useProviders();
  const { tasks, isLoading: tasksLoading } = useTasks();
  const [showBatchTasks, setShowBatchTasks] = useState(false);
  const scheduleQueries = useQueries({
    queries: providers.map((provider) => ({
      queryKey: ["schedules", provider.id],
      queryFn: () => api.listSchedules(provider.id),
      staleTime: 30_000,
    })),
  });
  const scheduledChecks = scheduleQueries.flatMap((query, index) => (query.data ?? [])
    .filter((schedule) => schedule.enabled)
    .map((schedule) => ({ schedule, providerName: providers[index]?.name ?? "Company" })));

  return (
    <main className="m3-scheduled-workspace min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[76rem] px-4 py-4 sm:px-5 sm:py-5 lg:px-6">
        <header className="m3-scheduled-header">
          <div>
            <p className="section-kicker">Automated work</p>
            <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight text-[var(--md-sys-color-on-surface)] sm:text-4xl">Scheduled</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">Review recurring policy checks, queued work, and batch tasks in one place.</p>
          </div>
          <MdFilledButton className="w-full sm:w-auto" onClick={() => setShowBatchTasks(true)}>Run a batch task</MdFilledButton>
        </header>

        <section className="m3-scheduled-section" aria-labelledby="scheduled-checks-heading">
          <div className="m3-scheduled-section-heading">
            <div>
              <p className="section-kicker">Recurring runs</p>
              <h2 id="scheduled-checks-heading" className="mt-1 font-display text-xl font-semibold">Scheduled policy checks</h2>
            </div>
            <span className="m3-count-badge data-value">{scheduledChecks.length}</span>
          </div>
          {scheduledChecks.length === 0 ? (
            <p className="m3-scheduled-empty">No recurring policy checks are scheduled. Turn on monitoring from a company’s research record to add one here.</p>
          ) : (
            <ul className="m3-scheduled-list">
              {scheduledChecks.map(({ schedule, providerName }) => <ScheduledCheck key={schedule.id} providerName={providerName} schedule={schedule} />)}
            </ul>
          )}
        </section>

        <section className="m3-scheduled-section" aria-labelledby="queued-work-heading">
          <div className="m3-scheduled-section-heading">
            <div>
              <p className="section-kicker">Task queue</p>
              <h2 id="queued-work-heading" className="mt-1 font-display text-xl font-semibold">Queued and recent work</h2>
            </div>
          </div>
          {tasksLoading ? <p className="m3-scheduled-empty">Loading task activity…</p> : tasks.length === 0 ? (
            <p className="m3-scheduled-empty">No queued or recent work.</p>
          ) : (
            <ul className="m3-scheduled-list">
              {tasks.map((task) => <li key={task.task_id} className="m3-scheduled-task"><div className="min-w-0"><p className="truncate text-sm font-semibold">{taskTitle(task)}</p><p className="mt-1 text-xs text-[var(--md-sys-color-on-surface-variant)]">{progressLabel(task) || "Finished task"}</p></div><span className={`m3-status-${task.status === "failed" || task.failed > 0 ? "error" : isTaskActive(task.status) ? "primary" : task.status === "done" ? "success" : "neutral"}`}>{taskState(task)}</span></li>)}
            </ul>
          )}
        </section>
      </div>
      {showBatchTasks && <BulkActionsModal onClose={() => setShowBatchTasks(false)} />}
    </main>
  );
}

function ScheduledCheck({ providerName, schedule }: { providerName: string; schedule: Schedule }) {
  const nextRun = schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "Awaiting schedule";
  return <li className="m3-scheduled-task"><div className="min-w-0"><p className="truncate text-sm font-semibold">{providerName}</p><p className="mt-1 text-xs text-[var(--md-sys-color-on-surface-variant)]">{schedule.cadence} · Next check {nextRun}</p></div><span className="m3-status-primary">Scheduled</span></li>;
}
