import { useEffect, useRef, useState } from "react";

import type { TaskState, TaskStatus } from "../api/types";
import { isRunTask, isTaskActive } from "../api/types";
import { useCancelTask, useTasks } from "../hooks/useTasks";
import { TaskOutputPanel } from "./TaskOutputPanel";
import { Tooltip } from "./Tooltip";

const STATUS_PILL: Record<TaskState, string> = {
  running: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300",
  cancelling: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  cancelled: "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  done: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
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
  const title = taskTitle(task);
  const canViewOutput = isTaskActive(task.status) || task.status === "failed" || task.failed > 0 || task.has_output;
  const linksToHistory = !!task.provider_id && isRunTask(task) && !!onViewRun;

  return (
    <li className="border-b border-slate-100 last:border-b-0 dark:border-slate-800">
      <div className="flex items-center gap-2 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm">{title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_PILL[task.status]}`}>
              {STATUS_LABEL[task.status]}
            </span>
            {progressText(task) && <span className="data-value text-xs text-slate-500 dark:text-slate-400">{progressText(task)}</span>}
            {task.failed > 0 && <span className="text-xs text-red-700 dark:text-red-400">{task.failed} failed</span>}
          </div>
          {task.error && <div className="mt-1 line-clamp-2 text-xs leading-4 text-red-700 dark:text-red-400">{task.error}</div>}
          {cancel.isError && <div role="alert" className="mt-1 text-xs leading-4 text-red-600 dark:text-red-400">{cancel.error instanceof Error ? cancel.error.message : "Could not cancel this task."}</div>}
        </div>
        <div className="flex flex-col items-stretch gap-1.5">
          {linksToHistory ? (
            <button type="button" className="btn-secondary min-h-9 px-2 py-1 text-xs" onClick={() => onViewRun?.(task)}>
              View in history
            </button>
          ) : canViewOutput ? (
            <button
              type="button"
              className="btn-secondary min-h-9 px-2 py-1 text-xs"
              aria-expanded={expanded}
              onClick={onToggleOutput}
            >
              {expanded ? "Hide output" : "Output"}
            </button>
          ) : null}
          {task.cancelable && (
            <button type="button" className="btn-secondary min-h-9 px-2 py-1 text-xs" disabled={cancel.isPending} onClick={() => cancel.mutate(task.task_id)}>
              Cancel
            </button>
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
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
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
            className={`fixed inset-x-3 top-[4.25rem] z-50 max-h-[calc(100dvh-5rem)] w-auto overflow-hidden rounded-md border border-slate-300 bg-white shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:z-20 sm:mt-2 sm:max-h-none sm:w-[min(20rem,calc(100vw-1.5rem))] dark:border-slate-700 dark:bg-slate-900 ${expandedTaskId ? "sm:w-[min(32rem,calc(100vw-2rem))]" : ""}`}
          >
            <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold dark:border-slate-800">
              Tasks {activeCount > 0 && <span className="font-normal text-slate-500 dark:text-slate-400">· {activeCount} active</span>}
            </div>
            {tasks.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">No recent tasks.</p>
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
