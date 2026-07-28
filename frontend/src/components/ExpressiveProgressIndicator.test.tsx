import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExpressiveProgressIndicator } from "./ExpressiveProgressIndicator";

describe("ExpressiveProgressIndicator", () => {
  it("exposes determinate progress to assistive technology", () => {
    const { container } = render(<ExpressiveProgressIndicator label="Analyze policy progress" value={0.42} />);

    expect(screen.getByRole("progressbar", { name: "Analyze policy progress" })).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByRole("progressbar", { name: "Analyze policy progress" })).toHaveAttribute("aria-valuetext", "42%");
    expect(container.querySelector(".m3-expressive-progress-track")).toHaveAttribute("x1", "264");
    expect(container.querySelector(".m3-expressive-progress-stop")).toHaveAttribute("cx", "594");
  });

  it("omits the current value while indeterminate", () => {
    render(<ExpressiveProgressIndicator label="Starting analysis" />);

    expect(screen.getByRole("progressbar", { name: "Starting analysis" })).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByRole("progressbar", { name: "Starting analysis" })).toHaveAttribute("aria-valuetext", "In progress");
  });

  it("clamps values to the supported range", () => {
    render(<ExpressiveProgressIndicator label="Completed analysis" value={1.5} />);

    expect(screen.getByRole("progressbar", { name: "Completed analysis" })).toHaveAttribute("aria-valuenow", "100");
  });
});
