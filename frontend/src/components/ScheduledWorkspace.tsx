import { useQueries } from "@tanstack/react-query";
import { useState, type CSSProperties } from "react";
import addTaskIcon from "@material-symbols/svg-400/rounded/add_task.svg?url";

import { api } from "../api/client";
import { isTaskActive, type Schedule, type TaskStatus } from "../api/types";
import { useProviders } from "../hooks/queries";
import { dismissTask, useDismissedTasks } from "../hooks/useDismissedTasks";
import { useTasks } from "../hooks/useTasks";
import { MdFilledTonalButton } from "./MaterialControls";
import { BulkActionsModal } from "./modals/BulkActionsModal";
import { TaskRow } from "./StatusCenter";

export function ScheduledWorkspace({ onViewRun }: { onViewRun?: (task: TaskStatus) => void }) {
  const { data: providers = [] } = useProviders();
  const { tasks, isLoading: tasksLoading } = useTasks();
  const [showBatchTasks, setShowBatchTasks] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const dismissedTaskIds = useDismissedTasks();
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
  const queuedTasks = tasks.filter((task) => isTaskActive(task.status));
  const recentTasks = tasks.filter((task) => !isTaskActive(task.status) && !dismissedTaskIds.has(task.task_id));
  const taskList = (items: TaskStatus[], dismissible = false) => (
    <ul className="m3-task-workspace-list">
      {items.map((task) => (
        <TaskRow
          key={task.task_id}
          task={task}
          expanded={expandedTaskId === task.task_id}
          onToggleOutput={() => setExpandedTaskId((current) => current === task.task_id ? null : task.task_id)}
          onViewRun={onViewRun}
          onDismiss={dismissible ? () => dismissTask(task.task_id) : undefined}
        />
      ))}
    </ul>
  );

  return (
    <main className="m3-page-pane m3-scheduled-workspace min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[76rem] px-4 py-4 sm:px-5 sm:py-5 lg:px-4 lg:py-4">
        <header className="m3-scheduled-header m3-mobile-page-intro">
          <div>
            <h1 className="m3-workspace-title">Tasks</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">Scheduled checks and task history.</p>
          </div>
          <MdFilledTonalButton className="m3-task-create-button" onClick={() => setShowBatchTasks(true)}>
            <span slot="icon" className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${addTaskIcon}")` } as CSSProperties} aria-hidden="true" />
            New task
          </MdFilledTonalButton>
        </header>

        <section className="m3-scheduled-section" aria-labelledby="scheduled-checks-heading">
          <div className="m3-scheduled-section-heading">
            <div>
              <h2 id="scheduled-checks-heading" className="font-display text-xl font-semibold">Scheduled</h2>
            </div>
            <span className="m3-count-badge data-value">{scheduledChecks.length}</span>
          </div>
          {scheduledChecks.length === 0 ? (
            <p className="m3-scheduled-empty">No scheduled checks. Turn on monitoring from a company record.</p>
          ) : (
            <ul className="m3-scheduled-list">
              {scheduledChecks.map(({ schedule, providerName }) => <ScheduledCheck key={schedule.id} providerName={providerName} schedule={schedule} />)}
            </ul>
          )}
        </section>

        <section className="m3-scheduled-section" aria-labelledby="queued-work-heading">
          <div className="m3-scheduled-section-heading">
            <h2 id="queued-work-heading" className="font-display text-xl font-semibold">Queued</h2>
            {queuedTasks.length > 0 ? <span className="m3-count-badge data-value">{queuedTasks.length}</span> : null}
          </div>
          {tasksLoading ? <p className="m3-scheduled-empty">Loading tasks…</p> : queuedTasks.length === 0
            ? <p className="m3-scheduled-empty">No queued tasks.</p>
            : taskList(queuedTasks)}
        </section>

        <section className="m3-scheduled-section" aria-labelledby="recent-work-heading">
          <div className="m3-scheduled-section-heading">
            <h2 id="recent-work-heading" className="font-display text-xl font-semibold">Recent</h2>
          </div>
          {tasksLoading ? <p className="m3-scheduled-empty">Loading tasks…</p> : recentTasks.length === 0
            ? <p className="m3-scheduled-empty">No recent tasks.</p>
            : taskList(recentTasks, true)}
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
