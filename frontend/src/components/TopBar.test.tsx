import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "./Tooltip";
import { TopBar } from "./TopBar";

vi.mock("./StatusCenter", () => ({
  StatusCenter: () => <button type="button" aria-label="Task activity">Activity</button>,
}));

function renderTopBar(workspace: "companies" | "collections" = "companies", options: { onBack?: () => void; showAddCompany?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onAddCompany = vi.fn();
  const result = render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <TopBar workspace={workspace} onAddCompany={onAddCompany} onBack={options.onBack} showAddCompany={options.showAddCompany} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { ...result, onAddCompany };
}

describe("TopBar contextual actions", () => {
  it("labels the active workspace without duplicating global navigation", () => {
    renderTopBar("collections");
    expect(screen.getByRole("heading", { name: "Collections" })).toBeVisible();
    expect(screen.queryByRole("navigation", { name: /research workspaces/i })).not.toBeInTheDocument();
  });

  it("has no automated accessibility violations in its default state", async () => {
    const { container } = renderTopBar();
    const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });

  it("keeps company creation available from the compact toolbar", async () => {
    const user = userEvent.setup();
    const { onAddCompany } = renderTopBar();
    const addButton = screen.getByRole("button", { name: "Add company" });
    expect(addButton).toHaveTextContent("Add");
    expect(screen.queryByRole("button", { name: "More ways to add companies" })).not.toBeInTheDocument();
    await user.click(addButton);
    expect(onAddCompany).toHaveBeenCalledOnce();
  });

  it("keeps the company action contextual to the companies workspace", () => {
    renderTopBar("collections");
    expect(screen.queryByRole("button", { name: "Add company" })).not.toBeInTheDocument();
  });

  it("uses the mobile app bar for back navigation and hides creation in company detail", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    renderTopBar("companies", { onBack, showAddCompany: false });
    expect(screen.queryByRole("button", { name: "Add company" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to companies" }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("leaves appearance preferences to app settings", () => {
    renderTopBar();
    expect(screen.queryByRole("button", { name: /theme/i })).not.toBeInTheDocument();
  });
});
