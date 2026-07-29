import { describe, expect, it } from "vitest";

import type { TaskStatus } from "../api/types";
import { taskPresentation, taskProgress } from "./taskPresentation";

function task(overrides: Partial<TaskStatus> = {}): TaskStatus {
  return {
    task_id: "task-1",
    status: "running",
    error: null,
    label: null,
    title: null,
    total: 1,
    completed: 0,
    failed: 0,
    ...overrides,
  };
}

describe("taskPresentation", () => {
  it("maps the comparison execution kind to company analysis terminology", () => {
    expect(taskPresentation(task({ kind: "comparison", provider_name: "Chick-fil-A", title: "Compare · Chick-fil-A" }))).toEqual({
      operation: "Company analysis",
      target: "Chick-fil-A",
    });
  });

  it("uses structured batch counts without separator punctuation", () => {
    expect(taskPresentation(task({ kind: "collection-analysis", total: 323, title: "Analyze · 323 companies" }))).toEqual({
      operation: "Company analysis",
      target: "323 companies",
    });
  });
});

describe("taskProgress", () => {
  it("keeps displayed and visual progress aligned at zero", () => {
    expect(taskProgress(task({ total: 1, completed: 0 }))).toMatchObject({ percentage: 0, value: 0, text: "0 of 1 (0%)" });
  });

  it("clamps invalid counts and over-complete work", () => {
    expect(taskProgress(task({ total: 4, completed: 9 }))).toMatchObject({ completed: 4, percentage: 100, value: 1 });
    expect(taskProgress(task({ total: 4, completed: -2 }))).toMatchObject({ completed: 0, percentage: 0, value: 0 });
  });

  it("uses indeterminate progress for unknown or invalid totals", () => {
    expect(taskProgress(task({ total: 0, completed: 0 }))).toBeNull();
    expect(taskProgress(task({ total: Number.NaN, completed: 0 }))).toBeNull();
  });
});
