import { useEffect, useId, useRef, useState } from "react";

export interface OverflowMenuItem {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
}

export function OverflowMenu({
  label,
  items,
  revealOnGroupHover = false,
}: {
  label: string;
  items: OverflowMenuItem[];
  revealOnGroupHover?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus();
    const closeOutside = (event: PointerEvent | FocusEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside, true);
    document.addEventListener("focusin", closeOutside, true);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside, true);
      document.removeEventListener("focusin", closeOutside, true);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const moveFocus = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])];
    if (!buttons.length) return;
    event.preventDefault();
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? buttons.length - 1
        : event.key === "ArrowDown" ? (current + 1) % buttons.length
          : (current - 1 + buttons.length) % buttons.length;
    buttons[next].focus();
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        className={`grid h-8 w-8 place-items-center rounded-md text-slate-400 transition hover:bg-slate-200/70 hover:text-slate-700 focus:opacity-100 dark:hover:bg-slate-700 dark:hover:text-slate-100 ${revealOnGroupHover && !open ? "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100" : ""}`}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor" aria-hidden="true">
          <circle cx="4" cy="10" r="1.5" /><circle cx="10" cy="10" r="1.5" /><circle cx="16" cy="10" r="1.5" />
        </svg>
      </button>
      {open && (
        <div
          ref={menuRef}
          id={id}
          role="menu"
          aria-label={label}
          className="absolute right-0 z-30 mt-1 min-w-40 rounded-md border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900"
          onKeyDown={moveFocus}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              className={`block w-full rounded px-3 py-2 text-left text-xs font-medium disabled:opacity-45 ${item.danger ? "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50" : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"}`}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
