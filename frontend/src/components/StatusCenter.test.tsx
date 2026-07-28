import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TaskStatus } from "../api/types";
import { TaskRow } from "./StatusCenter";

const mutate = vi.fn();

vi.mock("../hooks/useTasks", () => ({
  canRetryTask: (task: TaskStatus) => task.status === "failed" && task.kind === "score-all",
  useCancelTask: () => ({ isError: false, isPending: false, mutate }),
  useRetryTask: () => ({ error: null, isError: false, isPending: false, mutate }),
  useTasks: () => ({ activeCount: 0, tasks: [] }),
}));

vi.mock("../hooks/useDismissedTasks", () => ({
  useDismissedTasks: () => new Set<string>(),
}));

function task(overrides: Partial<TaskStatus>): TaskStatus {
  return {
    task_id: "task-1",
    status: "done",
    error: null,
    label: null,
    title: "Score all",
    total: 100,
    completed: 100,
    failed: 0,
    ...overrides,
  };
}

describe("TaskRow", () => {
  it("shows animated progress semantics only for active work", () => {
    const { container } = render(<TaskRow task={task({ status: "running", completed: 42, cancelable: true })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("In progress").querySelector(".m3-material-symbol")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Score all progress" })).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("42 of 100 · 42%")).toBeInTheDocument();
    expect(container.querySelector("md-outlined-button")?.textContent?.trim()).toBe("Details");
    expect(Array.from(container.querySelectorAll("md-outlined-button")).map((action) => action.textContent?.trim())).toEqual(["Details", "Cancel"]);
  });

  it("makes retry the primary first action for supported failures", () => {
    const { container } = render(<TaskRow task={task({ status: "failed", kind: "score-all", completed: 37, failed: 2, has_output: true })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("2 failed")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    const actions = Array.from(container.querySelectorAll("md-filled-button, md-outlined-button"));
    expect(screen.getByRole("group", { name: "Score all actions" })).toBeInTheDocument();
    expect(actions.map((action) => action.textContent?.trim())).toEqual(["Retry", "Details"]);
    expect(actions[0].tagName.toLowerCase()).toBe("md-filled-button");
    expect(actions[1].tagName.toLowerCase()).toBe("md-outlined-button");
  });

  it("keeps completed work quiet and does not offer retry", () => {
    render(<TaskRow task={task({ status: "done", has_output: false })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
