import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { TaskStatus } from "../api/types";

/**
 * Single-slot task runner for the bulk operations (Refresh Pending / Score All).
 * Runs one task at a time and polls until it settles, so the bulk operations
 * can't run concurrently with each other. `start` is a no-op while a task is
 * already in progress.
 */
export function useTaskRunner(onSettled?: () => void) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const busyRef = useRef(false);
  const settledRef = useRef(false);

  const { data: task } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId!),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : 1500;
    },
  });

  useEffect(() => {
    if (!task) return;
    if ((task.status === "done" || task.status === "failed") && !settledRef.current) {
      settledRef.current = true;
      busyRef.current = false;
      onSettled?.();
    }
  }, [task, onSettled]);

  const isRunning = busyRef.current || (!!task && task.status === "running");

  async function start(action: () => Promise<TaskStatus>) {
    if (busyRef.current) return; // a bulk operation is already running
    busyRef.current = true;
    settledRef.current = false;
    try {
      const started = await action();
      setTaskId(started.task_id);
    } catch (err) {
      busyRef.current = false;
      throw err;
    }
  }

  return { start, task, isRunning };
}
