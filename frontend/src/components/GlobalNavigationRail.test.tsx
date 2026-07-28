import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "./Tooltip";
import { GlobalNavigationRail } from "./GlobalNavigationRail";

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onWorkspaceChange = vi.fn();
  const result = render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <GlobalNavigationRail
          workspace="companies"
          onWorkspaceChange={onWorkspaceChange}
          onAddCompany={vi.fn()}
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { ...result, onWorkspaceChange };
}

describe("GlobalNavigationRail", () => {
  it("marks the active destination and changes destinations through the rail", async () => {
    const user = userEvent.setup();
    const { onWorkspaceChange } = renderRail();

    const primaryNavigation = screen.getAllByRole("navigation", { name: "Primary navigation" })[0];
    expect(within(primaryNavigation).getByRole("button", { name: "Companies" })).toHaveAttribute("aria-current", "page");
    await user.click(within(primaryNavigation).getByRole("button", { name: "Collections" }));
    expect(onWorkspaceChange).toHaveBeenCalledWith("collections");
    await user.click(within(primaryNavigation).getByRole("button", { name: "Tasks" }));
    expect(onWorkspaceChange).toHaveBeenCalledWith("scheduled");
  });

  it("keeps the primary creation action labeled", () => {
    renderRail();
    expect(screen.getByRole("button", { name: "Add company" })).toBeVisible();
  });

  it("light dismisses the split-button menu", async () => {
    const user = userEvent.setup();
    renderRail();

    await user.click(screen.getByRole("button", { name: "More ways to add companies" }));
    expect(screen.getByRole("menuitem", { name: "Import companies from CSV" })).toBeVisible();

    await user.click(document.body);
    expect(screen.queryByRole("menuitem", { name: "Import companies from CSV" })).not.toBeInTheDocument();
  });
});
