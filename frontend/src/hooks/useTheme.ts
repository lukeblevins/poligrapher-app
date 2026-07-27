import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "poligrapher-theme";
const SEED_COLOR_STORAGE_KEY = "poligrapher-theme-seed-color";
const SEED_COLOR_PATTERN = /^#[0-9a-f]{6}$/i;

function themeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function storedPreference(): ThemePreference {
  const value = themeStorage()?.getItem(STORAGE_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

function storedSeedColor(): string | null {
  const value = themeStorage()?.getItem(SEED_COLOR_STORAGE_KEY);
  return value && SEED_COLOR_PATTERN.test(value) ? value : null;
}

function rgbFromHex(hex: string) {
  return [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
}

function mixHex(base: string, seed: string, seedWeight: number) {
  const [baseRed, baseGreen, baseBlue] = rgbFromHex(base);
  const [seedRed, seedGreen, seedBlue] = rgbFromHex(seed);
  const mix = (baseChannel: number, seedChannel: number) => Math.round(baseChannel * (1 - seedWeight) + seedChannel * seedWeight);
  return `#${[mix(baseRed, seedRed), mix(baseGreen, seedGreen), mix(baseBlue, seedBlue)].map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function rgbToken(hex: string) {
  return rgbFromHex(hex).join(" ");
}

function contrastingForeground(hex: string) {
  const linear = rgbFromHex(hex).map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  const whiteContrast = 1.05 / (luminance + 0.05);
  const blackContrast = (luminance + 0.05) / 0.05;
  return whiteContrast >= blackContrast ? "#ffffff" : "#161d1b";
}

function applySeedColor(seedColor: string | null) {
  if (typeof document === "undefined") return;

  const root = document.documentElement.style;
  const properties = [
    "--md-sys-color-primary",
    "--md-sys-color-on-primary",
    "--md-sys-color-primary-container",
    "--md-sys-color-on-primary-container",
    "--md-sys-color-secondary",
    "--md-sys-color-on-secondary",
    "--md-sys-color-secondary-container",
    "--md-sys-color-on-secondary-container",
    "--md-sys-color-tertiary",
    "--md-sys-color-on-tertiary",
    "--md-sys-color-tertiary-container",
    "--md-sys-color-on-tertiary-container",
    "--md-sys-color-background",
    "--md-sys-color-surface",
    "--md-sys-color-surface-bright",
    "--md-sys-color-surface-dim",
    "--md-sys-color-surface-container-lowest",
    "--md-sys-color-surface-container-low",
    "--md-sys-color-surface-container",
    "--md-sys-color-surface-container-high",
    "--md-sys-color-surface-container-highest",
    "--md-sys-color-inverse-primary",
    "--canvas",
    "--surface",
    "--surface-subtle",
    "--surface-strong",
    "--accent",
    "--accent-hover",
    "--accent-soft",
    "--focus",
  ];

  if (!seedColor) {
    properties.forEach((property) => root.removeProperty(property));
    return;
  }

  const [red, green, blue] = rgbFromHex(seedColor);
  const dark = document.documentElement.dataset.theme === "dark";
  const surfaceBase = dark ? "#0e1513" : "#f4fbf8";
  const surfaceWeight = dark ? 0.12 : 0.055;
  const containerBase = dark
    ? ["#090f0d", "#161d1b", "#1a211f", "#242b29", "#2f3634"]
    : ["#ffffff", "#eef5f2", "#e8efec", "#e3e9e6", "#dde4e1"];
  const [lowest, low, container, high, highest] = containerBase.map((base, index) => mixHex(base, seedColor, surfaceWeight + index * 0.007));
  const surface = mixHex(surfaceBase, seedColor, surfaceWeight);
  root.setProperty("--md-sys-color-primary", seedColor);
  root.setProperty("--md-sys-color-on-primary", contrastingForeground(seedColor));
  root.setProperty("--md-sys-color-primary-container", `color-mix(in srgb, ${seedColor} 18%, var(--md-sys-color-surface))`);
  root.setProperty("--md-sys-color-on-primary-container", "var(--md-sys-color-on-surface)");
  root.setProperty("--md-sys-color-secondary", seedColor);
  root.setProperty("--md-sys-color-on-secondary", contrastingForeground(seedColor));
  root.setProperty("--md-sys-color-secondary-container", `color-mix(in srgb, ${seedColor} 18%, var(--md-sys-color-surface))`);
  root.setProperty("--md-sys-color-on-secondary-container", "var(--md-sys-color-on-surface)");
  root.setProperty("--md-sys-color-tertiary", seedColor);
  root.setProperty("--md-sys-color-on-tertiary", contrastingForeground(seedColor));
  root.setProperty("--md-sys-color-tertiary-container", `color-mix(in srgb, ${seedColor} 18%, var(--md-sys-color-surface))`);
  root.setProperty("--md-sys-color-on-tertiary-container", "var(--md-sys-color-on-surface)");
  root.setProperty("--md-sys-color-background", surface);
  root.setProperty("--md-sys-color-surface", surface);
  root.setProperty("--md-sys-color-surface-bright", mixHex(dark ? "#343b39" : "#f4fbf8", seedColor, surfaceWeight));
  root.setProperty("--md-sys-color-surface-dim", mixHex(dark ? "#0e1513" : "#d4dbd8", seedColor, surfaceWeight));
  root.setProperty("--md-sys-color-surface-container-lowest", lowest);
  root.setProperty("--md-sys-color-surface-container-low", low);
  root.setProperty("--md-sys-color-surface-container", container);
  root.setProperty("--md-sys-color-surface-container-high", high);
  root.setProperty("--md-sys-color-surface-container-highest", highest);
  root.setProperty("--md-sys-color-inverse-primary", seedColor);
  root.setProperty("--canvas", rgbToken(surface));
  root.setProperty("--surface", rgbToken(lowest));
  root.setProperty("--surface-subtle", rgbToken(low));
  root.setProperty("--surface-strong", rgbToken(high));
  root.setProperty("--accent", `${red} ${green} ${blue}`);
  root.setProperty("--accent-hover", `${red} ${green} ${blue}`);
  root.setProperty("--accent-soft", `${red} ${green} ${blue}`);
  root.setProperty("--focus", `${red} ${green} ${blue}`);
}

function applyPreference(preference: ThemePreference) {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  const dark = preference === "dark"
    || (preference === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function initializeTheme() {
  applyPreference(storedPreference());
  applySeedColor(storedSeedColor());
}

export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(storedPreference);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const syncSystem = () => {
      if (preference === "system") {
        applyPreference("system");
        applySeedColor(storedSeedColor());
      }
    };
    media.addEventListener("change", syncSystem);
    return () => media.removeEventListener("change", syncSystem);
  }, [preference]);

  const setPreference = (next: ThemePreference) => {
    const storage = themeStorage();
    if (next === "system") storage?.removeItem(STORAGE_KEY);
    else storage?.setItem(STORAGE_KEY, next);
    setPreferenceState(next);
    applyPreference(next);
    applySeedColor(storedSeedColor());
  };

  return { preference, setPreference };
}

export function useThemeSeedColor() {
  const [seedColor, setSeedColorState] = useState<string | null>(storedSeedColor);

  useEffect(() => {
    applySeedColor(seedColor);
  }, [seedColor]);

  const setSeedColor = (next: string) => {
    const normalized = next.toLowerCase();
    if (!SEED_COLOR_PATTERN.test(normalized)) return;
    themeStorage()?.setItem(SEED_COLOR_STORAGE_KEY, normalized);
    setSeedColorState(normalized);
  };

  const resetSeedColor = () => {
    themeStorage()?.removeItem(SEED_COLOR_STORAGE_KEY);
    setSeedColorState(null);
  };

  return { seedColor: seedColor ?? "#006a60", hasCustomSeedColor: seedColor !== null, setSeedColor, resetSeedColor };
}
