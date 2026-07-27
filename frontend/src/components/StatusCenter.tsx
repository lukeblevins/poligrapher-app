import { useEffect, useRef, useState, type CSSProperties } from "react";
import activityIcon from "@material-symbols/svg-400/rounded/monitoring.svg?url";
import cancelIcon from "@material-symbols/svg-400/rounded/close.svg?url";
import outputIcon from "@material-symbols/svg-400/rounded/article.svg?url";
import retryIcon from "@material-symbols/svg-400/rounded/refresh.svg?url";
import historyIcon from "@material-symbols/svg-400/rounded/history.svg?url";

import type { TaskState, TaskStatus } from "../api/types";
import { isRunTask, isTaskActive } from "../api/types";
import { useCancelTask, useRetryPendingTasks, useTasks } from "../hooks/useTasks";
import { TaskOutputPanel } from "./TaskOutputPanel";
import { Tooltip } from "./Tooltip";
import { MdFilledButton, MdLinearProgress, MdOutlinedButton } from "./MaterialControls";

const STATUS_PILL: Record<TaskState, string> = {
  running: "m3-status-primary",
  cancelling: "m3-status-warning",
  cancelled: "m3-status-neutral",
  done: "m3-status-success",
  failed: "m3-status-error",
};

const STATUS_LABEL: Record<TaskState, string> = {
  running: "running",
  cancelling: "cancelling…",
  cancelled: "cancelled",
  done: "done",
  failed: "failed",
};

function taskTitle(task: TaskStatus): string {
  return task.title ?? task.label ?? task.kind ?? "Task";
}

function MaterialIcon({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

function progressText(task: TaskStatus): string {
  if (task.total > 0) return `${task.completed}/${task.total}`;
  return isTaskActive(task.status) ? "…" : "";
}

function TaskRow({
  task,
  expanded,
  onToggleOutput,
  onViewRun,
}: {
  task: TaskStatus;
  expanded: boolean;
  onToggleOutput: () => void;
  onViewRun?: (task: TaskStatus) => void;
}) {
  const cancel = useCancelTask();
  const retryPending = useRetryPendingTasks();
  const title = taskTitle(task);
  const canViewOutput = isTaskActive(task.status) || task.status === "failed" || task.failed > 0 || task.has_output;
  const linksToHistory = !!task.provider_id && isRunTask(task) && !!onViewRun;
  const needsAttention = task.status === "failed" || task.failed > 0;
  const progress = task.total > 0 ? Math.min(100, Math.round((task.completed / task.total) * 100)) : null;

  return (
    <li className={`m3-task-banner ${needsAttention ? "m3-task-banner-error" : ""}`}>
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_PILL[task.status]}`}>
              {STATUS_LABEL[task.status]}
            </span>
            {progressText(task) && <span className="data-value text-xs text-[var(--md-sys-color-on-surface-variant)]">{progressText(task)}</span>}
          {task.failed > 0 && <span className="text-xs text-[var(--md-sys-color-error)]">{task.failed} failed</span>}
          </div>
          {progress !== null && <div className="m3-task-progress mt-3"><MdLinearProgress aria-label={`${title} progress`} value={progress / 100} /></div>}
          {progress === null && isTaskActive(task.status) && <div className="m3-task-progress mt-3"><MdLinearProgress aria-label={`${title} progress`} indeterminate /></div>}
          {task.error && <div className="mt-1 line-clamp-2 text-xs leading-4 text-[var(--md-sys-color-error)]">{task.error}</div>}
          {(cancel.isError || retryPending.isError) && <div role="alert" className="mt-1 text-xs leading-4 text-[var(--md-sys-color-error)]">{cancel.error instanceof Error ? cancel.error.message : retryPending.error instanceof Error ? retryPending.error.message : "Could not update this task."}</div>}
        </div>
        <div className="flex flex-none flex-wrap justify-end gap-1.5">
          {linksToHistory ? (
            <MdOutlinedButton className="m3-task-action min-h-9 text-xs" onClick={() => onViewRun?.(task)}><MaterialIcon src={historyIcon} />View run</MdOutlinedButton>
          ) : canViewOutput ? (
            <MdOutlinedButton
              className="m3-task-action min-h-9 text-xs"
              aria-expanded={expanded}
              onClick={onToggleOutput}
            ><MaterialIcon src={outputIcon} />{expanded ? "Hide details" : "Details"}</MdOutlinedButton>
          ) : null}
          {needsAttention && <MdFilledButton className="m3-task-action min-h-9 text-xs" disabled={retryPending.isPending} onClick={() => retryPending.mutate()}><MaterialIcon src={retryIcon} />{retryPending.isPending ? "Retrying…" : "Retry pending"}</MdFilledButton>}
          {task.cancelable && (
            <MdOutlinedButton className="m3-task-action min-h-9 text-xs" disabled={cancel.isPending} onClick={() => cancel.mutate(task.task_id)}><MaterialIcon src={cancelIcon} />Cancel</MdOutlinedButton>
          )}
        </div>
      </div>
      {expanded && <TaskOutputPanel task={task} context={title} compact />}
    </li>
  );
}

export function StatusCenter({ onViewRun }: { onViewRun?: (task: TaskStatus) => void }) {
  const { tasks, activeCount } = useTasks();
  const [open, setOpen] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        setExpandedTaskId(null);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const close = () => {
    setOpen(false);
    setExpandedTaskId(null);
  };

  return (
    <div className="relative">
      <Tooltip content="Task status" side="bottom" align="end" disabled={open}>
      <button
        ref={triggerRef}
        className="icon-button relative"
        onClick={() => {
          setOpen((value) => !value);
          if (open) setExpandedTaskId(null);
        }}
        aria-label="Task status center"
        aria-expanded={open}
        aria-controls="task-status-panel"
      >
        <MaterialIcon src={activityIcon} />
        {activeCount > 0 && <span aria-hidden="true" className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold leading-none text-white">{activeCount}</span>}
      </button>
      </Tooltip>
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {activeCount === 0 ? "No active tasks" : `${activeCount} active ${activeCount === 1 ? "task" : "tasks"}`}
      </span>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={close} aria-hidden="true" />
          <div
            id="task-status-panel"
            role="region"
            aria-label="Task status center"
            className={`m3-menu fixed inset-x-3 top-[4.25rem] z-50 max-h-[calc(100dvh-5rem)] w-auto overflow-hidden sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:z-20 sm:mt-2 sm:max-h-none sm:w-[min(20rem,calc(100vw-1.5rem))] ${expandedTaskId ? "sm:w-[min(32rem,calc(100vw-2rem))]" : ""}`}
          >
            <div className="m3-task-status-header px-4 py-3">
              <p className="text-sm font-semibold">Task activity</p>
              <p className="mt-0.5 text-xs text-[var(--md-sys-color-on-surface-variant)]">{activeCount > 0 ? `${activeCount} active ${activeCount === 1 ? "task" : "tasks"}` : "Recent and scheduled work"}</p>
            </div>
            {tasks.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-[var(--md-sys-color-on-surface-variant)]">No recent tasks.</p>
            ) : (
              <ul className="max-h-[calc(100dvh-8.5rem)] overflow-y-auto sm:max-h-[min(36rem,calc(100dvh-6rem))]">
                {tasks.map((task) => (
                  <TaskRow
                    key={task.task_id}
                    task={task}
                    expanded={expandedTaskId === task.task_id}
                    onToggleOutput={() => setExpandedTaskId((current) => current === task.task_id ? null : task.task_id)}
                    onViewRun={onViewRun ? (selected) => { close(); onViewRun(selected); } : undefined}
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
