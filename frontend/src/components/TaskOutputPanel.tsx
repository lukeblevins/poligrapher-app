import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import descriptionIcon from "@material-symbols/svg-400/rounded/description.svg?url";
import arrowDownIcon from "@material-symbols/svg-400/rounded/arrow_downward.svg?url";

import { api } from "../api/client";
import type { TaskStatus } from "../api/types";
import { isTaskActive } from "../api/types";

function MaterialIcon({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

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
    <section className={`m3-task-output ${compact ? "m3-task-output-compact" : ""}`} aria-label={`Task details for ${label}`}>
      <div className="m3-task-output-header">
        <span className="flex min-w-0 items-center gap-2">
          <MaterialIcon src={descriptionIcon} />
          <span className="truncate">Task details · {label}</span>
        </span>
        <span className="ml-3 shrink-0">{isTaskActive(status) ? "Live" : "Captured"}</span>
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
          className="m3-task-output-log"
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
            className="m3-task-output-jump"
            onClick={() => setFollowOutput(true)}
          >
            <MaterialIcon src={arrowDownIcon} />
            Latest
          </button>
        )}
      </div>
      <div className="m3-task-output-footer">
        <span>{isTaskActive(status) ? "Updates automatically while this run is active." : "Captured output is retained for troubleshooting."}</span>
        {data?.truncated && <span className="ml-3 shrink-0 text-[var(--md-sys-color-tertiary)]">Earlier output truncated</span>}
      </div>
    </section>
  );
}
