import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  className?: string;
  showCloseButton?: boolean;
}

export function Modal({ title, onClose, children, wide = false, className = "", showCloseButton = true }: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const initialFocus = closeRef.current ?? dialogRef.current;
    initialFocus?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary, textarea:not(:disabled), md-filled-button:not([disabled]), md-filled-tonal-button:not([disabled]), md-outlined-button:not([disabled]), md-text-button:not([disabled]), md-icon-button:not([disabled]), md-outlined-text-field:not([disabled]), md-checkbox:not([disabled]), md-radio:not([disabled]), md-switch:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-[color:rgb(0_0_0/0.32)] p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`ui-popover w-full ${wide ? "max-w-3xl" : "max-w-md"} max-h-[calc(100dvh-0.75rem)] overflow-y-auto rounded-t-[var(--md-sys-shape-corner-extra-large)] border-0 p-4 shadow-[var(--md-sys-elevation-level3)] outline-none sm:max-h-[calc(100dvh-2rem)] sm:rounded-[var(--md-sys-shape-corner-extra-large)] sm:p-6 ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="workspace-rule mb-5 flex items-center justify-between border-b pb-4">
          <h2 id={titleId} className="font-display text-xl font-semibold tracking-tight">{title}</h2>
          {showCloseButton && (
            <button
              ref={closeRef}
              className="icon-button -mr-1 -mt-1"
              onClick={onClose}
              aria-label={`Close ${title}`}
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4" aria-hidden="true">
                <path d="m5 5 10 10M15 5 5 15" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}
