import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useExpressivePress } from "./useExpressivePress";

function Harness() {
  useExpressivePress();
  return (
    <>
      <button type="button">Navigate</button>
      <button type="button" data-no-ripple>Scrim</button>
      {React.createElement("md-outlined-button", null, "Details")}
    </>
  );
}

afterEach(() => vi.useRealTimers());

describe("useExpressivePress", () => {
  it("applies and releases the expressive press state on native controls", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const button = screen.getByRole("button", { name: "Navigate" });

    fireEvent.pointerDown(button, { button: 0, clientX: 12, clientY: 8 });
    expect(button).toHaveClass("m3-expressive-pressed");

    fireEvent.pointerUp(button, { button: 0 });
    vi.advanceTimersByTime(400);
    expect(button).not.toHaveClass("m3-expressive-pressed");
  });

  it("supports keyboard presses and honors explicit ripple opt-out", () => {
    render(<Harness />);
    const button = screen.getByRole("button", { name: "Navigate" });
    const scrim = screen.getByRole("button", { name: "Scrim" });

    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.keyDown(scrim, { key: "Enter" });

    expect(button).toHaveClass("m3-expressive-pressed");
    expect(scrim).not.toHaveClass("m3-expressive-pressed");
  });
});
