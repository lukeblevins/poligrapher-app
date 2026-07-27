import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

if (typeof ElementInternals !== "undefined" && !ElementInternals.prototype.setFormValue) {
  Object.defineProperty(ElementInternals.prototype, "setFormValue", {
    configurable: true,
    value: () => undefined,
  });
}

afterEach(cleanup);
