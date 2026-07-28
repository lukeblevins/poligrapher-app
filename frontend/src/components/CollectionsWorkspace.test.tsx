import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SnackbarNotice } from "./CollectionsWorkspace";

describe("SnackbarNotice", () => {
  it("announces queued feedback and provides an accessible dismiss action", () => {
    const onDismiss = vi.fn();
    render(<SnackbarNotice message="Source verification queued." onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toHaveTextContent("Source verification queued.");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
