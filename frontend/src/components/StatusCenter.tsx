import { useEffect, useState } from "react";

import type { TaskState, TaskStatus } from "../api/types";
import { isTaskActive } from "../api/types";
import { useCancelTask, useTasks } from "../hooks/useTasks";

const STATUS_PILL: Record<TaskState, string> = {
  running: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  cancelling: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  cancelled: "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
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

function progressText(task: TaskStatus): string {
  if (task.total > 0) return `${task.completed}/${task.total}`;
  return isTaskActive(task.status) ? "…" : "";
}

function TaskRow({ task }: { task: TaskStatus }) {
  const cancel = useCancelTask();
  return (
    <li className="flex items-center gap-2 border-b border-zinc-100 px-3 py-2 last:border-b-0 dark:border-zinc-800">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{task.title ?? task.label ?? task.kind ?? "Task"}</div>
        <div className="mt-0.5 flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_PILL[task.status]}`}>
            {STATUS_LABEL[task.status]}
          </span>
          {progressText(task) && (
            <span className="text-xs text-zinc-400">{progressText(task)}</span>
          )}
          {task.failed > 0 && (
            <span className="text-xs text-red-500">{task.failed} failed</span>
          )}
        </div>
        {task.error && (
          <div className="mt-0.5 truncate text-xs text-red-500" title={task.error}>
            {task.error}
          </div>
        )}
      </div>
      {task.cancelable && (
        <button
          className="btn-secondary px-2 py-1 text-xs"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate(task.task_id)}
        >
          Cancel
        </button>
      )}
    </li>
  );
}

export function StatusCenter() {
  const { tasks, activeCount } = useTasks();
  const [open, setOpen] = useState(false);

  // Close on Escape for keyboard users.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="relative">
      <button
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        onClick={() => setOpen((v) => !v)}
        aria-label="Task status center"
        title="Task status"
      >
        {/* activity icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
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
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
            <div className="border-b border-zinc-100 px-3 py-2 text-sm font-medium dark:border-zinc-800">
              Tasks {activeCount > 0 && <span className="text-zinc-400">· {activeCount} active</span>}
            </div>
            {tasks.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-zinc-400">No recent tasks.</p>
            ) : (
              <ul className="max-h-96 overflow-y-auto">
                {tasks.map((t) => (
                  <TaskRow key={t.task_id} task={t} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
