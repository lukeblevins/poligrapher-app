import { useEffect, useState } from "react";

const STORAGE_KEY = "poligrapher.dismissed-recent-task-ids";
const CHANGE_EVENT = "poligrapher:dismissed-tasks-changed";

function loadDismissedTaskIds() {
  if (typeof window === "undefined") return new Set<string>();
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const taskIds = stored ? JSON.parse(stored) : [];
    return new Set<string>(Array.isArray(taskIds) ? taskIds.filter((id): id is string => typeof id === "string") : []);
  } catch {
    return new Set<string>();
  }
}

export function dismissTask(taskId: string) {
  const next = loadDismissedTaskIds().add(taskId);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useDismissedTasks() {
  const [taskIds, setTaskIds] = useState<Set<string>>(loadDismissedTaskIds);

  useEffect(() => {
    const refresh = () => setTaskIds(loadDismissedTaskIds());
    window.addEventListener(CHANGE_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(CHANGE_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  return taskIds;
}
