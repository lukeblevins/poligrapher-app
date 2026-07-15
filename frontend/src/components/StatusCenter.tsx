import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { TaskState, TaskStatus } from "../api/types";
import { isTaskActive } from "../api/types";
import { useCancelTask, useTasks } from "../hooks/useTasks";

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

function TaskRow({ task, onViewOutput }: { task: TaskStatus; onViewOutput: () => void }) {
  const cancel = useCancelTask();
  const title = taskTitle(task);
  const canViewOutput = isTaskActive(task.status) || task.status === "failed" || task.failed > 0 || task.has_output;

  return (
    <li className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 last:border-b-0 dark:border-slate-800">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_PILL[task.status]}`}>
            {STATUS_LABEL[task.status]}
          </span>
          {progressText(task) && (
            <span className="data-value text-xs text-slate-400">{progressText(task)}</span>
          )}
          {task.failed > 0 && (
            <span className="text-xs text-red-500">{task.failed} failed</span>
          )}
        </div>
        {task.error && (
          <div className="mt-1 line-clamp-2 text-xs leading-4 text-red-500" title={task.error}>
            {task.error}
          </div>
        )}
      </div>
      <div className="flex flex-col items-stretch gap-1.5">
        {canViewOutput && (
          <button
            type="button"
            className="btn-secondary min-h-7 px-2 py-1 text-xs"
            onClick={onViewOutput}
            aria-label={`View terminal output for ${title}`}
          >
            Output
          </button>
        )}
        {task.cancelable && (
          <button
            type="button"
            className="btn-secondary min-h-7 px-2 py-1 text-xs"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate(task.task_id)}
          >
            Cancel
          </button>
        )}
      </div>
    </li>
  );
}

function TaskOutputView({ task, onBack }: { task: TaskStatus; onBack: () => void }) {
  const outputRef = useRef<HTMLPreElement>(null);
  const [followOutput, setFollowOutput] = useState(true);
  const { data, error, isLoading } = useQuery({
    queryKey: ["task-output", task.task_id],
    queryFn: () => api.getTaskOutput(task.task_id),
    refetchInterval: (query) => isTaskActive(query.state.data?.status ?? task.status) ? 1000 : false,
  });
  const output = data?.output ?? "";
  const outputLines = output.trimEnd().split("\n");
  const latestLine = outputLines[outputLines.length - 1] ?? "";

  useEffect(() => {
    if (followOutput && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [followOutput, output]);

  return (
    <div>
      <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <button type="button" className="btn-secondary min-h-8 px-2.5 py-1 text-xs" onClick={onBack}>
          ← Tasks
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{taskTitle(task)}</div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
            <span className={`rounded px-1.5 py-0.5 ${STATUS_PILL[data?.status ?? task.status]}`}>
              {STATUS_LABEL[data?.status ?? task.status]}
            </span>
            <span>Terminal output</span>
          </div>
        </div>
      </div>

      <div className="relative bg-slate-950">
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {latestLine ? `Latest terminal output: ${latestLine}` : "Waiting for terminal output."}
        </div>
        <pre
          ref={outputRef}
          role="log"
          aria-live="off"
          aria-label={`Terminal output for ${taskTitle(task)}`}
          tabIndex={0}
          className="h-[min(24rem,calc(100vh-12rem))] min-h-48 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-5 text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-400"
          onScroll={(event) => {
            const element = event.currentTarget;
            setFollowOutput(element.scrollHeight - element.scrollTop - element.clientHeight < 32);
          }}
        >
          {isLoading ? "Loading terminal output…" : error ? `Unable to load terminal output: ${error instanceof Error ? error.message : "Unknown error"}` : output || "Waiting for terminal output…"}
        </pre>
        {!followOutput && (
          <button
            type="button"
            className="absolute bottom-3 right-3 rounded bg-slate-700 px-2.5 py-1.5 text-xs font-semibold text-white shadow hover:bg-slate-600"
            onClick={() => setFollowOutput(true)}
          >
            Jump to latest
          </button>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-slate-800 bg-slate-900 px-4 py-2 text-[11px] text-slate-400">
        <span>{isTaskActive(data?.status ?? task.status) ? "Updates automatically while the task runs." : "Captured output is retained for troubleshooting."}</span>
        {data?.truncated && <span className="text-amber-300">Earlier output truncated</span>}
      </div>
    </div>
  );
}

export function StatusCenter() {
  const { tasks, activeCount } = useTasks();
  const [open, setOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId) ?? null;

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        setSelectedTaskId(null);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const close = () => {
    setOpen(false);
    setSelectedTaskId(null);
  };

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        onClick={() => {
          setOpen((value) => !value);
          if (open) setSelectedTaskId(null);
        }}
        aria-label="Task status center"
        aria-expanded={open}
        aria-controls="task-status-panel"
        title="Task status"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
          aria-hidden="true"
        >
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
        {activeCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold leading-none text-white">
            {activeCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={close} aria-hidden="true" />
          <div
            id="task-status-panel"
            role="region"
            aria-label="Task status center"
            className={`z-20 overflow-hidden rounded-md border border-slate-300 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900 ${selectedTask ? "fixed left-1/2 top-20 w-[min(44rem,calc(100vw-2rem))] -translate-x-1/2" : "absolute right-0 mt-2 w-80"}`}
          >
            {selectedTask ? (
              <TaskOutputView task={selectedTask} onBack={() => setSelectedTaskId(null)} />
            ) : (
              <>
                <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold dark:border-slate-800">
                  Tasks {activeCount > 0 && <span className="font-normal text-slate-400">· {activeCount} active</span>}
                </div>
                {tasks.length === 0 ? (
                  <p className="px-4 py-8 text-center text-sm text-slate-400">No recent tasks.</p>
                ) : (
                  <ul className="max-h-96 overflow-y-auto">
                    {tasks.map((task) => (
                      <TaskRow key={task.task_id} task={task} onViewOutput={() => setSelectedTaskId(task.task_id)} />
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
