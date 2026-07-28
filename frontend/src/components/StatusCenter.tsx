import { useEffect, useRef, useState, type CSSProperties } from "react";
import activityIcon from "@material-symbols/svg-400/rounded/monitoring.svg?url";
import activityFilledIcon from "@material-symbols/svg-400/rounded/monitoring-fill.svg?url";
import cancelIcon from "@material-symbols/svg-400/rounded/close.svg?url";
import outputIcon from "@material-symbols/svg-400/rounded/article.svg?url";
import retryIcon from "@material-symbols/svg-400/rounded/refresh.svg?url";
import historyIcon from "@material-symbols/svg-400/rounded/history.svg?url";
import expandIcon from "@material-symbols/svg-400/rounded/open_in_full.svg?url";
import pendingIcon from "@material-symbols/svg-400/rounded/pending.svg?url";
import cancelledIcon from "@material-symbols/svg-400/rounded/cancel.svg?url";
import completedIcon from "@material-symbols/svg-400/rounded/check_circle.svg?url";
import failedIcon from "@material-symbols/svg-400/rounded/error.svg?url";

import type { TaskState, TaskStatus } from "../api/types";
import { isRunTask, isTaskActive } from "../api/types";
import { canRetryTask, useCancelTask, useRetryTask, useTasks } from "../hooks/useTasks";
import { useDismissedTasks } from "../hooks/useDismissedTasks";
import { ExpressiveProgressIndicator } from "./ExpressiveProgressIndicator";
import { TaskOutputPanel } from "./TaskOutputPanel";
import { Tooltip } from "./Tooltip";
import { MdFilledButton, MdOutlinedButton } from "./MaterialControls";

const STATUS_PILL: Record<TaskState, string> = {
  running: "m3-status-primary",
  cancelling: "m3-status-warning",
  cancelled: "m3-status-neutral",
  done: "m3-status-success",
  failed: "m3-status-error",
};

const STATUS_LABEL: Record<TaskState, string> = {
  running: "In progress",
  cancelling: "Cancelling…",
  cancelled: "Cancelled",
  done: "Completed",
  failed: "Failed",
};

const STATUS_ICON: Record<TaskState, string | null> = {
  running: null,
  cancelling: pendingIcon,
  cancelled: cancelledIcon,
  done: completedIcon,
  failed: failedIcon,
};

function taskTitle(task: TaskStatus): string {
  return task.title ?? task.label ?? task.kind ?? "Task";
}

function MaterialIcon({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

function progressText(task: TaskStatus): string {
  if (task.total <= 0 || !isTaskActive(task.status)) return "";
  const percentage = Math.round((task.completed / task.total) * 100);
  return `${task.completed} of ${task.total} · ${percentage}%`;
}

export function TaskRow({
  task,
  expanded,
  onToggleOutput,
  onViewRun,
  onDismiss,
}: {
  task: TaskStatus;
  expanded: boolean;
  onToggleOutput: () => void;
  onViewRun?: (task: TaskStatus) => void;
  onDismiss?: () => void;
}) {
  const cancel = useCancelTask();
  const retryTask = useRetryTask(task);
  const title = taskTitle(task);
  const canViewOutput = isTaskActive(task.status) || task.status === "failed" || task.failed > 0 || task.has_output;
  const linksToHistory = !!task.provider_id && isRunTask(task) && !!onViewRun;
  const needsAttention = task.status === "failed" || task.failed > 0;
  const progress = task.total > 0 ? Math.min(100, Math.round((task.completed / task.total) * 100)) : null;
  const statusIcon = STATUS_ICON[task.status];

  return (
    <li className={`m3-task-banner m3-task-banner-${task.status} ${needsAttention ? "m3-task-banner-error" : ""} ${onDismiss ? "m3-task-banner-dismissible" : ""}`}>
      {onDismiss ? (
        <button type="button" className="m3-task-dismiss-button" aria-label={`Dismiss ${title}`} title="Dismiss" onClick={onDismiss}>
          <MaterialIcon src={cancelIcon} />
        </button>
      ) : null}
      <div className="m3-task-banner-content">
        <div className="min-w-0 flex-1">
          <div className="m3-task-title">{title}</div>
          <div className="m3-task-meta">
            <span className={`m3-task-status ${STATUS_PILL[task.status]}`}>
              {statusIcon ? <MaterialIcon src={statusIcon} /> : null}
              {STATUS_LABEL[task.status]}
            </span>
            {task.failed > 0 && <span className="m3-task-failure-count">{task.failed} failed</span>}
          </div>
          {isTaskActive(task.status) && progress !== null && <ExpressiveProgressIndicator label={`${title} progress`} value={progress / 100} />}
          {isTaskActive(task.status) && progress === null && <ExpressiveProgressIndicator label={`${title} progress`} />}
          {progressText(task) && <p className="data-value mt-1.5 text-xs text-[var(--md-sys-color-on-surface-variant)]">{progressText(task)}</p>}
          {task.error && <div className="mt-2 text-xs leading-5 text-[var(--md-sys-color-error)]">{task.error}</div>}
          {(cancel.isError || retryTask.isError) && <div role="alert" className="mt-1 text-xs leading-4 text-[var(--md-sys-color-error)]">{cancel.error instanceof Error ? cancel.error.message : retryTask.error instanceof Error ? retryTask.error.message : "Could not update this task."}</div>}
        </div>
        <div className="m3-task-actions" role="group" aria-label={`${title} actions`}>
          {canRetryTask(task) && <MdFilledButton className="m3-task-action m3-task-action-primary" disabled={retryTask.isPending} onClick={() => retryTask.mutate()}><span className="m3-task-action-label"><MaterialIcon src={retryIcon} />{retryTask.isPending ? "Retrying…" : "Retry"}</span></MdFilledButton>}
          {linksToHistory ? (
            <MdOutlinedButton className="m3-task-action" onClick={() => onViewRun?.(task)}><span className="m3-task-action-label"><MaterialIcon src={historyIcon} />View run</span></MdOutlinedButton>
          ) : canViewOutput ? (
            <MdOutlinedButton
              className="m3-task-action"
              aria-expanded={expanded}
              onClick={onToggleOutput}
            ><span className="m3-task-action-label"><MaterialIcon src={outputIcon} />{expanded ? "Hide details" : "Details"}</span></MdOutlinedButton>
          ) : null}
          {task.cancelable && (
            <MdOutlinedButton className="m3-task-action" disabled={cancel.isPending} onClick={() => cancel.mutate(task.task_id)}><span className="m3-task-action-label"><MaterialIcon src={cancelIcon} />Cancel</span></MdOutlinedButton>
          )}
        </div>
      </div>
      {expanded && <TaskOutputPanel task={task} context={title} compact />}
    </li>
  );
}

export function StatusCenter({ onViewRun, onOpenWorkspace, variant = "topbar" }: { onViewRun?: (task: TaskStatus) => void; onOpenWorkspace?: () => void; variant?: "topbar" | "rail" }) {
  const { tasks, activeCount } = useTasks();
  const dismissedTaskIds = useDismissedTasks();
  const visibleTasks = tasks.filter((task) => !dismissedTaskIds.has(task.task_id));
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

  const navigationVariant = variant === "rail";

  return (
    <div className={`relative ${variant === "rail" ? "m3-task-rail" : ""}`}>
      <Tooltip content="Task activity" side={variant === "rail" ? "right" : "bottom"} align={variant === "rail" ? "center" : "end"} disabled={open}>
      <button
        ref={triggerRef}
        className={navigationVariant ? `m3-task-utility-button relative ${open ? "m3-task-utility-button-selected" : ""}` : "icon-button relative"}
        onClick={() => {
          setOpen((value) => !value);
          if (open) setExpandedTaskId(null);
        }}
        aria-label="Open task activity"
        aria-expanded={open}
        aria-controls="task-status-panel"
      >
        <span className={`${navigationVariant ? "m3-rail-icon" : ""} relative`}>
          <MaterialIcon src={open ? activityFilledIcon : activityIcon} />
          {activeCount > 0 && <span aria-hidden="true" className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold leading-none text-white">{activeCount}</span>}
        </span>
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
            className={`m3-menu z-50 max-h-[calc(100dvh-5rem)] overflow-hidden ${variant === "rail" ? `absolute bottom-0 left-[calc(100%+0.5rem)] w-[min(28rem,calc(100vw-8rem))] ${expandedTaskId ? "sm:w-[min(44rem,calc(100vw-8rem))]" : ""}` : `fixed inset-x-3 top-[4.25rem] w-auto sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:z-20 sm:mt-2 sm:max-h-none sm:w-[min(28rem,calc(100vw-2rem))] ${expandedTaskId ? "sm:w-[min(44rem,calc(100vw-2rem))]" : ""}`}`}
          >
            <div className="m3-task-status-header flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">Task activity</p>
                <p className="mt-0.5 text-xs text-[var(--md-sys-color-on-surface-variant)]">{activeCount > 0 ? `${activeCount} active ${activeCount === 1 ? "task" : "tasks"}` : "Recent and scheduled work"}</p>
              </div>
              {onOpenWorkspace ? (
                <button type="button" className="m3-task-expand-button" aria-label="Open Tasks page" title="Open Tasks page" onClick={() => { close(); onOpenWorkspace(); }}>
                  <MaterialIcon src={expandIcon} />
                </button>
              ) : null}
            </div>
            {visibleTasks.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-[var(--md-sys-color-on-surface-variant)]">No recent tasks.</p>
            ) : (
              <ul className="max-h-[calc(100dvh-8.5rem)] overflow-y-auto sm:max-h-[min(36rem,calc(100dvh-6rem))]">
                {visibleTasks.map((task) => (
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
