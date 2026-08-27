import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BulkActionPreview } from "../api/types";
import { CollectionAnalysisAction } from "./CollectionAnalysisAction";
import { SnackbarNotice } from "./CollectionsWorkspace";

const analysisPreview: BulkActionPreview = {
  operation: "generate",
  provider_count: 50,
  eligible_count: 9,
  skipped_count: 41,
  collection_count: 1,
  providers: [],
  skipped: [],
};

describe("SnackbarNotice", () => {
  it("announces queued feedback and provides an accessible dismiss action", () => {
    const onDismiss = vi.fn();
    render(<SnackbarNotice message="Source verification queued." onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toHaveTextContent("Source verification queued.");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

describe("CollectionAnalysisAction", () => {
  it("shows canonical collection eligibility before the user queues work", () => {
    const onReview = vi.fn();
    render(
      <CollectionAnalysisAction
        preview={analysisPreview}
        isLoading={false}
        isError={false}
        confirming={false}
        isPending={false}
        error={null}
        onReview={onReview}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "9 companies are ready to analyze" })).toBeVisible();
    expect(screen.getByText(/41 companies stay untouched/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Review & queue" }));
    expect(onReview).toHaveBeenCalledOnce();
  });

  it("keeps final queue confirmation inside the collection surface", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <CollectionAnalysisAction
        preview={analysisPreview}
        isLoading={false}
        isError={false}
        confirming
        isPending={false}
        error={null}
        onReview={vi.fn()}
        onCancel={onCancel}
        onConfirm={onConfirm}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole("group", { name: "Confirm collection analysis" })).toHaveTextContent("Existing graph output will not be regenerated.");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm and queue" }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("does not offer a queue action when no companies are eligible", () => {
    render(
      <CollectionAnalysisAction
        preview={{ ...analysisPreview, eligible_count: 0, skipped_count: 50 }}
        isLoading={false}
        isError={false}
        confirming={false}
        isPending={false}
        error={null}
        onReview={vi.fn()}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Collection analysis is up to date" })).toBeVisible();
    expect(screen.queryByText("Review & queue")).not.toBeInTheDocument();
  });
});
