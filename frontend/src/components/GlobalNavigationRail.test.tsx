import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GlobalNavigationRail } from "./GlobalNavigationRail";

describe("GlobalNavigationRail", () => {
  it("marks the active destination and changes destinations through the rail", async () => {
    const user = userEvent.setup();
    const onWorkspaceChange = vi.fn();
    render(<GlobalNavigationRail workspace="companies" onWorkspaceChange={onWorkspaceChange} onAddCompany={vi.fn()} />);

    const primaryNavigation = screen.getAllByRole("navigation", { name: "Primary navigation" })[0];
    expect(within(primaryNavigation).getByRole("button", { name: "Companies" })).toHaveAttribute("aria-current", "page");
    await user.click(within(primaryNavigation).getByRole("button", { name: "Collections" }));
    expect(onWorkspaceChange).toHaveBeenCalledWith("collections");
    await user.click(within(primaryNavigation).getByRole("button", { name: "Scheduled" }));
    expect(onWorkspaceChange).toHaveBeenCalledWith("scheduled");
  });

  it("keeps the primary creation action labeled", () => {
    render(<GlobalNavigationRail workspace="companies" onWorkspaceChange={vi.fn()} onAddCompany={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Add company" })).toBeVisible();
  });
});
