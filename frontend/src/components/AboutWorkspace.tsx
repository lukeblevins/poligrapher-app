import { useState, type CSSProperties } from "react";
import deleteHistoryIcon from "@material-symbols/svg-400/rounded/delete_sweep.svg?url";

import { SOURCES } from "./AttributionModal";
import { useTheme, useThemeSeedColor, type ThemePreference } from "../hooks/useTheme";
import { RetentionCleanupModal } from "./modals/RetentionCleanupModal";

const APPEARANCE_OPTIONS: Array<{ value: ThemePreference; label: string; description: string }> = [
  { value: "system", label: "System", description: "Follow your device setting" },
  { value: "light", label: "Light", description: "Always use the light theme" },
  { value: "dark", label: "Dark", description: "Always use the dark theme" },
];

export function AboutWorkspace() {
  const { preference, setPreference } = useTheme();
  const { seedColor, hasCustomSeedColor, setSeedColor, resetSeedColor } = useThemeSeedColor();
  const [showRetentionCleanup, setShowRetentionCleanup] = useState(false);

  return (
    <main className="m3-page-pane min-w-0 flex-1 overflow-y-auto px-4 py-4 sm:px-8 sm:py-8 lg:px-4 lg:py-4">
      <section className="max-w-3xl">
        <h1 className="m3-mobile-redundant-title m3-workspace-title">App settings</h1>
        <p className="m3-settings-summary mt-3 max-w-2xl text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
          Personalize the app and review its data sources.
        </p>

        <section className="mt-8" aria-labelledby="appearance-heading">
          <h2 id="appearance-heading" className="font-display text-xl font-semibold">Appearance</h2>
          <p className="mt-1 text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
            Choose when the app uses light or dark colors.
          </p>
          <div className="m3-appearance-options mt-4" role="group" aria-label="Color mode">
            {APPEARANCE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className="m3-appearance-option"
                aria-pressed={preference === option.value}
                onClick={() => setPreference(option.value)}
              >
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="mt-8" aria-labelledby="theme-color-heading">
          <h2 id="theme-color-heading" className="font-display text-xl font-semibold">Theme color</h2>
          <p className="mt-1 text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
            Choose the seed color used for the app’s Material color palette.
          </p>
          <div className="m3-theme-picker mt-4">
            <input aria-label="Theme seed color" type="color" value={seedColor} onChange={(event) => setSeedColor(event.currentTarget.value)} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--md-sys-color-on-surface)]">Custom theme color</p>
              <p className="text-sm text-[var(--md-sys-color-on-surface-variant)]">{hasCustomSeedColor ? seedColor.toUpperCase() : "Default teal"}</p>
            </div>
            {hasCustomSeedColor && <button type="button" className="m3-theme-reset" onClick={resetSeedColor}>Reset</button>}
          </div>
        </section>

        <section className="mt-10" aria-labelledby="retention-heading">
          <h2 id="retention-heading" className="font-display text-xl font-semibold">Data retention</h2>
          <p className="mt-1 text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
            Manage how much policy history and stored analysis data the app keeps.
          </p>
          <button type="button" className="m3-settings-action mt-4" onClick={() => setShowRetentionCleanup(true)}>
            <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${deleteHistoryIcon}")` } as CSSProperties} aria-hidden="true" />
            <span><strong>Delete old history</strong><small>Review and remove records older than a selected period</small></span>
          </button>
        </section>

        <section className="mt-10" aria-labelledby="sources-heading">
          <h2 id="sources-heading" className="font-display text-xl font-semibold">Data sources and attribution</h2>
          <div className="mt-4 grid gap-3">
            {SOURCES.map((source) => (
              <article key={source.name} className="rounded-[var(--md-sys-shape-corner-large)] bg-[var(--md-sys-color-surface-container)] p-4">
                <a href={source.href} target="_blank" rel="noreferrer" className="text-sm font-semibold text-[var(--md-sys-color-primary)] hover:underline">{source.name}</a>
                <p className="mt-1 text-sm leading-5 text-[var(--md-sys-color-on-surface-variant)]">{source.description}</p>
              </article>
            ))}
          </div>
        </section>
      </section>
      {showRetentionCleanup && <RetentionCleanupModal onClose={() => setShowRetentionCleanup(false)} />}
    </main>
  );
}
