import arrowBackIcon from "@material-symbols/svg-400/rounded/arrow_back.svg?url";
import type { CSSProperties } from "react";

export function TopBar({ workspace, onAddCompany, onBack, showAddCompany = true }: { workspace: "companies" | "collections" | "scheduled" | "about"; onAddCompany: () => void; onBack?: () => void; showAddCompany?: boolean }) {
  return (
    <header className="app-masthead relative z-40 flex h-16 flex-shrink-0 items-center justify-between gap-2 px-4 sm:hidden">
      {onBack ? (
        <button type="button" className="m3-mobile-appbar-back" aria-label="Back to companies" onClick={onBack}>
          <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${arrowBackIcon}")` } as CSSProperties} aria-hidden="true" />
        </button>
      ) : null}
      <div className="min-w-0"><h1 className="m3-mobile-appbar-title truncate">{workspace === "companies" ? "Companies" : workspace === "collections" ? "Collections" : workspace === "scheduled" ? "Tasks" : "Settings"}</h1></div>
      <div className="ml-auto" />
      {workspace === "companies" && showAddCompany ? (
        <button type="button" className="m3-mobile-add-fab sm:hidden" aria-label="Add company" title="Add company" onClick={onAddCompany}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M10 4v12M4 10h12" strokeLinecap="round" /></svg><span>Add</span></button>
      ) : null}
    </header>
  );
}
