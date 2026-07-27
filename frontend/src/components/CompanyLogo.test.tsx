import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompanyLogo } from "./CompanyLogo";

describe("CompanyLogo", () => {
  it("removes the fallback lettermark after a company logo loads", () => {
    render(<CompanyLogo name="Example Company" domain="example.com" />);

    expect(screen.getByText("EC")).toBeInTheDocument();
    const image = document.querySelector("img");
    expect(image).not.toBeNull();
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 32 });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 32 });
    fireEvent.load(image!);

    expect(screen.queryByText("EC")).not.toBeInTheDocument();
  });

  it("keeps the lettermark when no safe logo domain is available", () => {
    render(<CompanyLogo name="Example Company" domain="not a domain" />);

    expect(screen.getByText("EC")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
