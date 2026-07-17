import { useEffect, useId, useRef, useState } from "react";

export interface SelectMenuOption {
  value: string;
  label: string;
}

export function SelectMenu({
  label,
  heading,
  value,
  options,
  onChange,
  className = "",
  align = "left",
  disabled = false,
}: {
  label: string;
  heading?: string;
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  className?: string;
  align?: "left" | "right";
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLButtonElement>('[data-selected="true"]')?.focus();

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
    const options = [...(listRef.current?.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)') ?? [])];
    if (!options.length) return;
    event.preventDefault();
    const current = options.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? options.length - 1
        : event.key === "ArrowDown" ? (current + 1) % options.length
          : (current - 1 + options.length) % options.length;
    options[next].focus();
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        className="form-input flex items-center justify-between gap-2 py-1.5 text-left text-xs disabled:cursor-not-allowed disabled:opacity-45"
        aria-label={`${label}: ${selected?.label ?? "No selection"}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="truncate">{selected?.label ?? "Select"}</span>
        <svg className={`h-3.5 w-3.5 flex-none text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M5.22 7.22a.75.75 0 0 1 1.06 0L10 10.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 8.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <div
          ref={listRef}
          id={id}
          role="listbox"
          aria-label={label}
          className={`absolute z-50 mt-1 min-w-full w-max max-w-[min(18rem,calc(100vw-1.5rem))] overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900 ${align === "right" ? "right-0" : "left-0"}`}
          onKeyDown={moveFocus}
        >
          {heading && (
            <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200">
              {heading}
            </div>
          )}
          <div className="max-h-[min(18rem,calc(100dvh-7rem))] overflow-y-auto p-1.5">
            {options.map((option) => {
              const isSelected = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  data-selected={isSelected}
                  className={`flex min-h-9 w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                    isSelected
                      ? "bg-teal-50 font-semibold text-teal-800 dark:bg-teal-950/50 dark:text-teal-200"
                      : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                  }`}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                    triggerRef.current?.focus();
                  }}
                >
                  <span>{option.label}</span>
                  {isSelected && (
                    <svg className="h-3.5 w-3.5 flex-none" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="m3.5 8 2.75 2.75L12.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
