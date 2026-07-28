import { useEffect } from "react";

const CONTROL_SELECTOR = [
  "button:not([data-no-ripple])",
  "summary:not([data-no-ripple])",
  "md-filled-button:not([data-no-ripple])",
  "md-filled-tonal-button:not([data-no-ripple])",
  "md-outlined-button:not([data-no-ripple])",
  "md-text-button:not([data-no-ripple])",
  "md-icon-button:not([data-no-ripple])",
].join(", ");
const RELEASE_DELAY_MS = 400;

export function useExpressivePress() {
  useEffect(() => {
    const releaseTimers = new Set<number>();
    const activeControls = new Set<HTMLElement>();

    const controlFor = (target: EventTarget | null) =>
      target instanceof Element ? target.closest<HTMLElement>(CONTROL_SELECTOR) : null;

    const beginPress = (control: HTMLElement, clientX?: number, clientY?: number) => {
      if (control.matches(":disabled, [aria-disabled='true']")) return;
      const bounds = control.getBoundingClientRect();
      const x = clientX === undefined ? bounds.width / 2 : clientX - bounds.left;
      const y = clientY === undefined ? bounds.height / 2 : clientY - bounds.top;
      control.style.setProperty("--m3-press-x", `${x}px`);
      control.style.setProperty("--m3-press-y", `${y}px`);
      control.classList.remove("m3-expressive-pressed");
      void control.offsetWidth;
      control.classList.add("m3-expressive-pressed");
      activeControls.add(control);
    };

    const endPress = (control: HTMLElement | null) => {
      if (!control) return;
      const timer = window.setTimeout(() => {
        control.classList.remove("m3-expressive-pressed");
        activeControls.delete(control);
        releaseTimers.delete(timer);
      }, RELEASE_DELAY_MS);
      releaseTimers.add(timer);
    };

    const onPointerDown = (event: PointerEvent) => {
      const control = controlFor(event.target);
      if (!control || event.button !== 0) return;
      beginPress(control, event.clientX, event.clientY);
    };
    const onPointerEnd = () => activeControls.forEach(endPress);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || (event.key !== "Enter" && event.key !== " ")) return;
      const control = controlFor(event.target);
      if (control) beginPress(control);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") endPress(controlFor(event.target));
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointerup", onPointerEnd, true);
    document.addEventListener("pointercancel", onPointerEnd, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", onPointerEnd);
    document.documentElement.classList.add("m3-expressive-motion");

    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("pointerup", onPointerEnd, true);
      document.removeEventListener("pointercancel", onPointerEnd, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", onPointerEnd);
      document.documentElement.classList.remove("m3-expressive-motion");
      releaseTimers.forEach(window.clearTimeout);
      document.querySelectorAll(".m3-expressive-pressed").forEach((control) => control.classList.remove("m3-expressive-pressed"));
    };
  }, []);
}
