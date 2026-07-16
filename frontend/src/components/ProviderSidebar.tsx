import { useEffect, useRef, useState } from "react";

import type { Provider } from "../api/types";
import { useCollections, useDeleteProvider, useProviders } from "../hooks/queries";
import { CompanyLogo } from "./CompanyLogo";
import { Modal } from "./Modal";
import { OverflowMenu } from "./OverflowMenu";
import { Tooltip } from "./Tooltip";

interface Props {
  selectedId: string | null;
  onSelect: (provider: Provider) => void;
  onDeleted?: (id: string) => void;
}

interface IndustryOption {
  key: string;
  label: string;
}

function normalizeIndustry(value: string): string {
  return value.trim().toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/g, "");
}

function getIndustryOptions(providers: Provider[]): IndustryOption[] {
  const groupedLabels = new Map<string, Map<string, number>>();

  for (const provider of providers) {
    const label = provider.industry?.trim();
    if (!label) continue;

    const key = normalizeIndustry(label);
    if (!key) continue;

    const labels = groupedLabels.get(key) ?? new Map<string, number>();
    labels.set(label, (labels.get(label) ?? 0) + 1);
    groupedLabels.set(key, labels);
  }

  return [...groupedLabels.entries()]
    .map(([key, labels]) => ({
      key,
      label: [...labels.entries()]
        .sort(([leftLabel, leftCount], [rightLabel, rightCount]) =>
          rightCount - leftCount || leftLabel.localeCompare(rightLabel),
        )[0][0],
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

function companyHealth(p: Provider): { color: string; label: string; detail: string } {
  const allFailed = p.policy_count > 0 && p.failed_count === p.policy_count;
  const mixedResults = p.failed_count > 0 && p.succeeded_count > 0;
  const sourceLabel = p.source_status === "available" ? `Available${p.source_http_status ? ` (HTTP ${p.source_http_status})` : ""}`
    : p.source_status === "restricted" ? "Restricted"
      : p.source_status === "broken" ? "Not found"
        : p.source_status === "error" ? "Check failed"
          : p.source_status === "missing" ? "Not configured"
            : "Not checked";
  const analysisLabel = p.policy_count === 0 ? "No analyses"
    : `${p.succeeded_count} succeeded, ${p.failed_count} failed`;
  if (["broken", "error"].includes(p.source_status) || allFailed) {
    return { color: "bg-red-500", label: "Needs attention", detail: `Source: ${sourceLabel}. Analyses: ${analysisLabel}.` };
  }
  if (p.source_status === "restricted" || mixedResults || p.failed_count > 0) {
    return { color: "bg-amber-400", label: "Attention recommended", detail: `Source: ${sourceLabel}. Analyses: ${analysisLabel}.` };
  }
  if (p.source_status === "available") {
    return { color: "bg-teal-500", label: "Ready", detail: `Source: ${sourceLabel}. Analyses: ${analysisLabel}.` };
  }
  return { color: "bg-slate-300 dark:bg-slate-600", label: "Not ready", detail: `Source: ${sourceLabel}. Analyses: ${analysisLabel}.` };
}

function logoDomain(p: Provider): string | null {
  if (p.domain) return p.domain;
  if (!p.source_url) return null;
  try {
    return new URL(p.source_url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

export function ProviderSidebar({ selectedId, onSelect, onDeleted }: Props) {
  const { data: providers = [], isLoading } = useProviders();
  const { data: collections = [] } = useCollections();
  const deleteProvider = useDeleteProvider();
  const [query, setQuery] = useState("");
  const [collectionId, setCollectionId] = useState("all");
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [industryMenuOpen, setIndustryMenuOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);
  const industryMenuRef = useRef<HTMLDivElement>(null);
  const industryButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!industryMenuOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!industryMenuRef.current?.contains(event.target as Node)) {
        setIndustryMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIndustryMenuOpen(false);
        industryButtonRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [industryMenuOpen]);

  const selectedCollection = collections.find((collection) => collection.id === collectionId);
  const collectionMembers = selectedCollection ? new Set(selectedCollection.provider_ids) : null;
  const industries = getIndustryOptions(providers);
  const industryLabels = new Map(industries.map((industry) => [industry.key, industry.label]));
  const selectedIndustrySet = new Set(selectedIndustries);
  const industryLabel = selectedIndustries.length === 0
    ? "All industries"
    : selectedIndustries.length === 1
      ? industries.find((industry) => industry.key === selectedIndustries[0])?.label ?? selectedIndustries[0]
      : `${selectedIndustries.length} industries`;
  const needle = query.toLowerCase();
  const filtered = providers.filter((provider) =>
    (!collectionMembers || collectionMembers.has(provider.id))
    && (selectedIndustries.length === 0 || (!!provider.industry && selectedIndustrySet.has(normalizeIndustry(provider.industry))))
    && (provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle))),
  );

  const toggleIndustry = (industry: string) => {
    setSelectedIndustries((current) => current.includes(industry)
      ? current.filter((value) => value !== industry)
      : [...current, industry]);
  };

  return (
    <aside className="flex w-72 flex-shrink-0 flex-col border-r border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="border-b border-slate-100 px-4 py-4 dark:border-slate-800">
        <div className="mb-2.5 flex items-center justify-between px-0.5">
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">Companies</span>
          <span
            className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            aria-live="polite"
            aria-atomic="true"
            aria-label={`${filtered.length} companies shown`}
          >
            {filtered.length}
          </span>
        </div>
        <input
          type="search"
          className="form-input"
          placeholder="Search companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label>
            <span className="sr-only">Company collection</span>
            <select className="form-input py-1.5 text-xs" value={collectionId} onChange={(event) => setCollectionId(event.target.value)}>
              <option value="all">All collections</option>
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
            </select>
          </label>
          <div className="relative" ref={industryMenuRef}>
            <button
              ref={industryButtonRef}
              type="button"
              className="form-input flex items-center justify-between gap-2 py-1.5 text-left text-xs"
              aria-label={`Filter by industries, ${industryLabel}`}
              aria-expanded={industryMenuOpen}
              aria-controls="industry-filter-menu"
              onClick={() => setIndustryMenuOpen((open) => !open)}
            >
              <span className="truncate">{industryLabel}</span>
              <svg className={`h-3.5 w-3.5 flex-none text-slate-400 transition-transform ${industryMenuOpen ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M5.22 7.22a.75.75 0 0 1 1.06 0L10 10.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 8.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
              </svg>
            </button>
            {industryMenuOpen && (
              <div
                id="industry-filter-menu"
                className="absolute right-0 z-30 mt-1 w-64 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900"
              >
                <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2 dark:border-slate-800">
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">Industries</span>
                  <button
                    type="button"
                    className="text-[11px] font-semibold text-teal-700 hover:text-teal-900 disabled:cursor-default disabled:text-slate-300 dark:text-teal-300 dark:hover:text-teal-100 dark:disabled:text-slate-600"
                    disabled={selectedIndustries.length === 0}
                    onClick={() => setSelectedIndustries([])}
                  >
                    Clear
                  </button>
                </div>
                <fieldset className="max-h-64 overflow-y-auto p-1.5">
                  <legend className="sr-only">Industries to show</legend>
                  {industries.map((industry) => (
                    <label key={industry.key} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-slate-300 accent-teal-600 dark:border-slate-600"
                        checked={selectedIndustrySet.has(industry.key)}
                        onChange={() => toggleIndustry(industry.key)}
                      />
                      <span>{industry.label}</span>
                    </label>
                  ))}
                </fieldset>
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-sm text-slate-400">Loading…</p>}
        {!isLoading && filtered.length === 0 && (
          <p className="p-4 text-sm text-slate-400">No companies.</p>
        )}
        {filtered.map((p) => {
          const health = companyHealth(p);
          return (
          <div
            key={p.id}
            className={`group relative flex items-center border-l-2 pr-2 text-sm transition-colors ${
              selectedId === p.id
                ? "border-teal-600 bg-teal-50/70 font-semibold text-slate-950 dark:border-teal-400 dark:bg-teal-950/30 dark:text-white"
                : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-900"
            }`}
          >
            <Tooltip
              side="right"
              align="center"
              content={(
                <>
                  <div className="font-semibold text-white">{health.label}</div>
                  <div className="mt-1 text-slate-200">{health.detail}</div>
                </>
              )}
            >
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500"
              onClick={() => onSelect(p)}
              aria-current={selectedId === p.id ? "true" : undefined}
            >
              <span className="relative flex-shrink-0">
                <CompanyLogo name={p.name} domain={logoDomain(p)} />
                <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white dark:border-slate-950 ${health.color}`} aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{p.name}</span>
                <span className="mt-0.5 block truncate text-xs font-normal text-slate-400 dark:text-slate-500">
                  {p.ticker ? `${p.ticker} · ` : ""}{p.industry ? industryLabels.get(normalizeIndustry(p.industry)) ?? p.industry : "Uncategorized"} · {p.policy_count} results
                </span>
              </span>
            </button>
            </Tooltip>
            <OverflowMenu
              label={`Actions for ${p.name}`}
              revealOnGroupHover
              items={[{ label: "Delete company", danger: true, onSelect: () => setDeleteTarget(p) }]}
            />
          </div>
        );})}
      </div>
      {deleteTarget && (
        <Modal title="Delete company" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            Delete {deleteTarget.name} and all of its policy analyses? This can’t be undone.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button
              type="button"
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              disabled={deleteProvider.isPending}
              onClick={() => deleteProvider.mutate(deleteTarget.id, {
                onSuccess: () => {
                  onDeleted?.(deleteTarget.id);
                  setDeleteTarget(null);
                },
              })}
            >
              {deleteProvider.isPending ? "Deleting…" : "Delete"}
            </button>
          </div>
        </Modal>
      )}
    </aside>
  );
}
