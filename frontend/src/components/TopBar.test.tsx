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

function renderTopBar(workspace: "companies" | "collections" = "companies") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onAddCompany = vi.fn();
  const result = render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <TopBar workspace={workspace} onAddCompany={onAddCompany} />
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
    await user.click(screen.getByRole("button", { name: "Add company" }));
    expect(onAddCompany).toHaveBeenCalledOnce();
  });

  it("applies explicit light and dark themes without relying on the OS media query", async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByRole("button", { name: /system theme.*switch to light/i }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    await user.click(screen.getByRole("button", { name: /light theme.*switch to dark/i }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});
