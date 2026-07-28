import { describe, expect, it } from "vitest";

import type { TaskStatus } from "../api/types";
import { canRetryTask } from "./useTasks";

function task(overrides: Partial<TaskStatus>): TaskStatus {
  return {
    task_id: "task-1",
    status: "failed",
    error: null,
    label: null,
    total: 10,
    completed: 3,
    failed: 1,
    ...overrides,
  };
}

describe("canRetryTask", () => {
  it("offers retry for failed tasks with a supported rerun path", () => {
    expect(canRetryTask(task({ kind: "score-all" }))).toBe(true);
    expect(canRetryTask(task({ kind: "comparison", provider_id: "provider-1", run_id: "run-1" }))).toBe(true);
  });

  it("does not offer retry for cancelled, completed, or upload tasks", () => {
    expect(canRetryTask(task({ status: "cancelled", kind: "score-all" }))).toBe(false);
    expect(canRetryTask(task({ status: "done", kind: "refresh" }))).toBe(false);
    expect(canRetryTask(task({ kind: "upload", provider_id: "provider-1" }))).toBe(false);
  });
});
