import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Policy } from "../api/types";
import { api } from "../api/client";
import { DetailPane } from "./DetailPane";

vi.mock("../api/client", () => ({
  api: { downloadGraphArtifacts: vi.fn() },
}));

vi.mock("./MaterialControls", () => ({
  MdOutlinedButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));

vi.mock("./GraphViewer", () => ({ GraphViewer: () => <div>Graph viewer</div> }));
vi.mock("./StatsPanel", () => ({ StatsPanel: () => <div>Statistics</div> }));
vi.mock("./AssessmentsPanel", () => ({ AssessmentsPanel: () => <div>Assessments</div> }));

function policy(overrides: Partial<Policy> = {}): Policy {
  return {
    id: "policy-1",
    provider_id: "provider-1",
    url: "https://example.com/privacy",
    source: "webpage",
    method: "website",
    run_group: null,
    rerun_of_policy_id: null,
    scheduled: false,
    content_hash: null,
    capture_date: "2026-08-17",
    has_results: true,
    pipeline_status: "succeeded",
    pipeline_errors: [],
    privacy_score: null,
    gdpr_score: null,
    graph_kind: "standard",
    graph_artifacts_available: true,
    created_at: "2026-08-17T00:00:00Z",
    ...overrides,
  };
}

describe("DetailPane graph artifacts", () => {
  it("hides the action when no retained graph archive exists", () => {
    render(<DetailPane policy={policy({ graph_artifacts_available: false })} providerName="Example" onClose={vi.fn()} />);
    expect(screen.queryByText("Download graph artifacts")).not.toBeInTheDocument();
  });

  it("downloads the public graph-only archive", async () => {
    vi.mocked(api.downloadGraphArtifacts).mockResolvedValue({
      blob: new Blob(["zip"]),
      filename: "policy-1-graph-artifacts.zip",
    });
    const createObjectURL = vi.fn(() => "blob:graph");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<DetailPane policy={policy()} providerName="Example" onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Download graph artifacts"));

    await waitFor(() => expect(api.downloadGraphArtifacts).toHaveBeenCalledWith("policy-1"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:graph");
  });

  it("reports a failed blob download without closing the report", async () => {
    vi.mocked(api.downloadGraphArtifacts).mockRejectedValue(new Error("404: No graph artifact archive found"));
    render(<DetailPane policy={policy()} providerName="Example" onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Download graph artifacts"));
    expect(await screen.findByRole("alert")).toHaveTextContent("No graph artifact archive found");
    expect(screen.getByRole("dialog", { name: "Analysis details" })).toBeInTheDocument();
  });
});
