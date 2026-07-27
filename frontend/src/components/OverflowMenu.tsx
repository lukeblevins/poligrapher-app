import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import moreIcon from "@material-symbols/svg-400/rounded/more_vert.svg?url";
import { Tooltip } from "./Tooltip";

export interface OverflowMenuItem {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
}

function MaterialSymbol({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
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
      <Tooltip content={label} side="bottom" align="end" disabled={open}>
      <button
        ref={triggerRef}
        type="button"
        className={`icon-button h-10 w-10 ${revealOnGroupHover && !open ? "opacity-60 hover:opacity-100 focus:opacity-100" : ""}`}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <MaterialSymbol src={moreIcon} />
      </button>
      </Tooltip>
      {open && (
        <div
          ref={menuRef}
          id={id}
          role="menu"
          aria-label={label}
          className="m3-menu absolute right-0 z-30 mt-1 min-w-40 overflow-hidden py-2"
          onKeyDown={moveFocus}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              className={`m3-menu-item block w-full px-3 py-2 text-left text-sm disabled:opacity-45 ${item.danger ? "m3-menu-item-danger" : ""}`}
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
