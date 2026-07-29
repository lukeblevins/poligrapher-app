import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TaskStatus } from "../api/types";
import { TaskRow } from "./StatusCenter";

const mutate = vi.fn();

vi.mock("../hooks/useTasks", () => ({
  canRetryTask: (task: TaskStatus) => task.status === "failed" && task.kind === "score-all",
  useCancelTask: () => ({ isError: false, isPending: false, mutate }),
  useRetryTask: () => ({ error: null, isError: false, isPending: false, mutate }),
  useRetryFailedSubtasks: () => ({ error: null, isError: false, isPending: false, mutate }),
  useTasks: () => ({ activeCount: 0, tasks: [] }),
}));

vi.mock("../hooks/useDismissedTasks", () => ({
  useDismissedTasks: () => new Set<string>(),
}));

vi.mock("./TaskOutputPanel", () => ({
  TaskOutputPanel: ({ context }: { context: string }) => <div data-testid="task-output">{context}</div>,
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
    expect(screen.getByText("42 of 100 (42%)")).toBeInTheDocument();
    expect(Array.from(container.querySelectorAll("md-text-button")).map((action) => action.textContent?.trim())).toEqual(["Details", "Cancel"]);
  });

  it("makes retry the primary first action for supported failures", () => {
    const { container } = render(<TaskRow task={task({ status: "failed", kind: "score-all", completed: 37, failed: 2, has_output: true })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("2 failed")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    const actions = Array.from(container.querySelectorAll("md-filled-button, md-text-button"));
    expect(screen.getByRole("group", { name: "Score all actions" })).toBeInTheDocument();
    expect(actions.map((action) => action.textContent?.trim())).toEqual(["Retry", "Details"]);
    expect(actions[0].tagName.toLowerCase()).toBe("md-filled-button");
    expect(actions[1].tagName.toLowerCase()).toBe("md-text-button");
  });

  it("uses analysis terminology and structured company identity for legacy comparison tasks", () => {
    render(<TaskRow task={task({ status: "running", kind: "comparison", title: "Compare · Chick-fil-A", provider_name: "Chick-fil-A", total: 1, completed: 0 })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("Company analysis")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chick-fil-A" })).toBeInTheDocument();
    expect(screen.queryByText(/Compare|·/)).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Company analysis: Chick-fil-A progress" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("0 of 1 (0%)")).toBeInTheDocument();
  });

  it("shows running batch failures as secondary metadata", () => {
    render(<TaskRow task={task({ status: "running", kind: "collection-analysis", title: "Analyze 323 companies", total: 323, completed: 201, failed: 96, has_output: true })} expanded={true} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("96 failed")).toHaveClass("m3-task-failure-count");
    expect(screen.getByText("Collapse details")).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps completed work quiet and does not offer retry", () => {
    render(<TaskRow task={task({ status: "done", has_output: false })} expanded={false} onToggleOutput={vi.fn()} onDismiss={vi.fn()} />);

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss Score all" })).toBeInTheDocument();
  });

  it("shows standardized next steps and retries only transient collection failures", () => {
    const { container } = render(<TaskRow task={task({
      status: "done",
      outcome: "partially_succeeded",
      kind: "collection-analysis",
      failed: 2,
      issues: [
        {
          issue_id: "issue-1",
          code: "crawl.navigation_failed",
          stage: "acquisition",
          severity: "error",
          retryability: "transient",
          summary: "The policy page could not be loaded.",
          technical_detail: "net::ERR_TIMED_OUT",
          provider_id: "provider-1",
          policy_id: null,
          actions: [{ action: "retry", label: "Retry failed companies" }],
          occurred_at: null,
        },
      ],
    })} expanded={false} onToggleOutput={vi.fn()} />);

    expect(screen.getByText("Completed with issues")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Recommended next steps" })).toHaveTextContent("The policy page could not be loaded.");
    expect(Array.from(container.querySelectorAll("md-filled-button")).map((action) => action.textContent?.trim())).toEqual(["Retry failed"]);
  });
});
