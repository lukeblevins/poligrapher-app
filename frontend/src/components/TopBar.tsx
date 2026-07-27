import type { TaskStatus } from "../api/types";
import { useTheme } from "../hooks/useTheme";
import { StatusCenter } from "./StatusCenter";

export function TopBar({ workspace, onAddCompany, onViewRun }: { workspace: "companies" | "collections" | "scheduled" | "about"; onAddCompany: () => void; onViewRun?: (task: TaskStatus) => void }) {
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();
  const nextTheme = themePreference === "system" ? "light" : themePreference === "light" ? "dark" : "system";
  const themeLabel = themePreference === "system" ? "System theme" : themePreference === "light" ? "Light theme" : "Dark theme";

  return (
    <header className="app-masthead relative z-40 flex h-16 flex-shrink-0 items-center justify-between gap-2 px-4 sm:px-6">
      <div className="min-w-0 sm:hidden"><h1 className="truncate font-display text-base font-medium text-[var(--md-sys-color-on-surface)]">{workspace === "companies" ? "Companies" : workspace === "collections" ? "Collections" : workspace === "scheduled" ? "Scheduled" : "Settings"}</h1></div>
      <div className="ml-auto flex flex-none items-center gap-1 sm:gap-2">
        <StatusCenter onViewRun={onViewRun} />
        <button type="button" className="masthead-button min-w-10 px-2.5" aria-label={`${themeLabel}. Switch to ${nextTheme} theme`} title={`${themeLabel} · switch to ${nextTheme}`} onClick={() => setThemePreference(nextTheme)}>
          {themePreference === "dark" ? <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><path d="M16 12.3A7 7 0 0 1 7.7 4a6 6 0 1 0 8.3 8.3Z" strokeLinecap="round" strokeLinejoin="round" /></svg> : themePreference === "light" ? <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><circle cx="10" cy="10" r="3" /><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M15.7 4.3l-1.4 1.4M5.7 14.3l1.4-1.4" strokeLinecap="round" /></svg> : <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><rect x="2.5" y="4" width="15" height="10" rx="1.5" /><path d="M7 17h6M10 14v3" strokeLinecap="round" /></svg>}
        </button>
        <button type="button" className="m3-compact-create sm:hidden" aria-label="Add company" title="Add company" onClick={onAddCompany}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4" aria-hidden="true"><path d="M10 4v12M4 10h12" strokeLinecap="round" /></svg></button>
      </div>
    </header>
  );
}
