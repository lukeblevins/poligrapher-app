import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { TaskStatus } from "../api/types";
import { isTaskActive } from "../api/types";

export function TaskOutputPanel({
  task,
  context,
  compact = false,
}: {
  task: TaskStatus;
  context?: string;
  compact?: boolean;
}) {
  const outputRef = useRef<HTMLPreElement>(null);
  const [followOutput, setFollowOutput] = useState(true);
  const { data, error, isLoading } = useQuery({
    queryKey: ["task-output", task.task_id],
    queryFn: () => api.getTaskOutput(task.task_id),
    refetchInterval: (query) => isTaskActive(query.state.data?.status ?? task.status) ? 1000 : false,
  });
  const status = data?.status ?? task.status;
  const output = data?.output ?? "";
  const lines = output.trimEnd().split("\n");
  const latestLine = lines[lines.length - 1] ?? "";
  const label = context ?? task.provider_name ?? task.title ?? task.label ?? "task";

  useEffect(() => {
    if (followOutput && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [followOutput, output]);

  return (
    <div className="overflow-hidden border-t border-slate-800 bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-3 py-2 text-[11px] text-slate-400">
        <span className="flex min-w-0 items-center gap-2">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 text-teal-400" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="m3 4 3.5 4L3 12M8 12h5" />
          </svg>
          <span className="truncate">PoliGraph worker · {label}</span>
        </span>
        <span className="ml-3 shrink-0">{isTaskActive(status) ? "Following output" : "Run log"}</span>
      </div>
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {latestLine ? `Latest terminal output: ${latestLine}` : "Waiting for terminal output."}
      </div>
      <div className="relative">
        <pre
          ref={outputRef}
          role="log"
          aria-live="off"
          aria-label={`PoliGraph terminal output for ${label}, run ${task.task_id}`}
          tabIndex={0}
          className={`${compact ? "h-52" : "h-[min(24rem,calc(100vh-20rem))] min-h-40"} overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-5 text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-400`}
          onScroll={(event) => {
            const element = event.currentTarget;
            setFollowOutput(element.scrollHeight - element.scrollTop - element.clientHeight < 32);
          }}
        >
          {isLoading
            ? "Loading terminal output…"
            : error
              ? `Unable to load terminal output: ${error instanceof Error ? error.message : "Unknown error"}`
              : output || "Waiting for terminal output…"}
        </pre>
        {!followOutput && (
          <button
            type="button"
            className="absolute bottom-3 right-3 rounded bg-slate-700 px-2.5 py-1.5 text-xs font-semibold text-white shadow hover:bg-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
            onClick={() => setFollowOutput(true)}
          >
            Jump to latest
          </button>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-slate-800 bg-slate-900 px-3 py-2 text-[11px] text-slate-400">
        <span>{isTaskActive(status) ? "Updates automatically while this run is active." : "Captured output is retained for troubleshooting."}</span>
        {data?.truncated && <span className="ml-3 shrink-0 text-amber-300">Earlier output truncated</span>}
      </div>
    </div>
  );
}
