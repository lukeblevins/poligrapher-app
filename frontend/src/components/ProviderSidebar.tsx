import { useEffect, useMemo, useState, type CSSProperties } from "react";
import filterIcon from "@material-symbols/svg-400/rounded/filter_alt.svg?url";

import type { Provider } from "../api/types";
import { useCollections, useDeleteProvider, useProviders } from "../hooks/queries";
import { CompanyLogo } from "./CompanyLogo";
import { Modal } from "./Modal";
import { OverflowMenu } from "./OverflowMenu";
import { SelectMenu } from "./SelectMenu";
import { MdFilledButton, MdOutlinedButton } from "./MaterialControls";

interface Props {
  selectedId: string | null;
  onSelect: (provider: Provider) => void;
  onDeleted?: (id: string) => void;
  mobileHidden?: boolean;
}

const PROVIDER_BATCH_SIZE = 100;

function MaterialSymbol({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
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

function logoDomain(p: Provider): string | null {
  if (p.domain) return p.domain;
  if (!p.source_url) return null;
  try {
    return new URL(p.source_url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

export function ProviderSidebar({ selectedId, onSelect, onDeleted, mobileHidden = false }: Props) {
  const { data: providers = [], isLoading, isError, error } = useProviders();
  const { data: collections = [] } = useCollections();
  const deleteProvider = useDeleteProvider();
  const [query, setQuery] = useState("");
  const [collectionId, setCollectionId] = useState("all");
  const [selectedIndustry, setSelectedIndustry] = useState("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);
  const [visibleCount, setVisibleCount] = useState(PROVIDER_BATCH_SIZE);
  const industries = useMemo(() => getIndustryOptions(providers), [providers]);
  const filtered = useMemo(() => {
    const selectedCollection = collections.find((collection) => collection.id === collectionId);
    const collectionMembers = selectedCollection ? new Set(selectedCollection.provider_ids) : null;
    const needle = query.toLowerCase();
    return providers.filter((provider) =>
      (!collectionMembers || collectionMembers.has(provider.id))
      && (selectedIndustry === "all" || (!!provider.industry && selectedIndustry === normalizeIndustry(provider.industry)))
      && (provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle))),
    );
  }, [collectionId, collections, providers, query, selectedIndustry]);
  const visibleProviders = filtered.slice(0, visibleCount);
  const hasActiveFilters = collectionId !== "all" || selectedIndustry !== "all";

  function clearFilters() {
    setCollectionId("all");
    setSelectedIndustry("all");
    setFiltersOpen(false);
  }

  useEffect(() => {
    setVisibleCount(PROVIDER_BATCH_SIZE);
  }, [query, collectionId, selectedIndustry]);

  useEffect(() => {
    if (!selectedId) return;
    const selectedIndex = filtered.findIndex((provider) => provider.id === selectedId);
    if (selectedIndex >= visibleCount) {
      setVisibleCount(Math.ceil((selectedIndex + 1) / PROVIDER_BATCH_SIZE) * PROVIDER_BATCH_SIZE);
    }
  }, [filtered, selectedId, visibleCount]);

  return (
    <aside
      aria-label="Company browser"
      className={`${mobileHidden ? "hidden lg:flex" : "flex"} m3-list-detail-pane ui-subtle w-full flex-shrink-0 flex-col sm:w-[calc(100%-1rem)] lg:w-[clamp(20rem,26vw,24rem)]`}
    >
      <div className="px-4 pt-4">
        <div className="m3-company-list-heading mb-2.5 flex items-center justify-between">
          <span className="m3-workspace-title">Companies</span>
          <span
            className="m3-count-badge"
            aria-live="polite"
            aria-atomic="true"
            aria-label={`${filtered.length} companies shown`}
          >
            {filtered.length}
          </span>
        </div>
        <label className="m3-contained-search">
          <svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="M784-120 532-372q-30 24-69 38t-83 14q-109 0-184.5-75.5T120-580q0-109 75.5-184.5T380-840q109 0 184.5 75.5T640-580q0 44-14 83t-38 69l252 252-56 56ZM380-400q75 0 127.5-52.5T560-580q0-75-52.5-127.5T380-760q-75 0-127.5 52.5T200-580q0 75 52.5 127.5T380-400Z" /></svg>
          <input id="company-search" type="search" value={query} placeholder="Search companies" aria-label="Search companies" onChange={(event) => setQuery(event.target.value)} />
          <span className="m3-mobile-company-count m3-count-badge" aria-hidden="true">{filtered.length}</span>
        </label>
        <button type="button" className="m3-filter-button mt-2" aria-expanded={filtersOpen} aria-controls="company-filters" onClick={() => setFiltersOpen((open) => !open)}>
          <MaterialSymbol src={filterIcon} />
          <span>Filter</span>
          {hasActiveFilters && <span className="m3-filter-active-dot" aria-label="Filters applied" />}
        </button>
        {filtersOpen && (
          <div id="company-filters" className="m3-filter-disclosure">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-[var(--md-sys-color-on-surface-variant)]">Filter companies</p>
              <button type="button" className="m3-filter-clear" disabled={!hasActiveFilters} onClick={clearFilters}>Clear all filters</button>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <SelectMenu
                label="Collection"
                heading="Collections"
                value={collectionId}
                options={[
                  { value: "all", label: "All" },
                  ...collections.map((collection) => ({ value: collection.id, label: collection.name })),
                ]}
                onChange={setCollectionId}
              />
              <SelectMenu label="Industry" value={selectedIndustry} options={[{ value: "all", label: "All industries" }, ...industries.map((industry) => ({ value: industry.key, label: industry.label }))]} onChange={setSelectedIndustry} />
            </div>
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && <p role="status" className="p-4 text-sm text-[var(--md-sys-color-on-surface-variant)]">Loading companies…</p>}
        {isError && (
          <div role="alert" className="m-4 status-error">
            Could not load companies. {error instanceof Error ? error.message : "Try refreshing the page."}
          </div>
        )}
        {!isLoading && !isError && filtered.length === 0 && (
          <p className="m-4 quiet-state py-6">No companies match these filters.</p>
        )}
        {visibleProviders.map((p) => {
          return (
          <div
            key={p.id}
            className={`m3-navigation-item group relative mx-2 my-1 flex min-h-16 items-center pr-1.5 text-sm ${
              selectedId === p.id
                ? "m3-navigation-item-selected font-medium"
                : ""
            }`}
          >
            <button
              type="button"
              className="m3-company-list-content"
              onClick={() => onSelect(p)}
              aria-current={selectedId === p.id ? "true" : undefined}
            >
              <span className="flex-shrink-0"><CompanyLogo name={p.name} domain={logoDomain(p)} /></span>
              <span className="min-w-0 flex-1">
                <span className="m3-company-list-name">{p.name}</span>
                <span className="m3-company-list-meta">
                  {p.ticker && <span className="m3-company-ticker">{p.ticker}</span>}
                  <span className={`m3-industry-chip ${p.industry ? "" : "m3-industry-chip-neutral"}`}>
                    {p.industry ?? "Uncategorized"}
                  </span>
                </span>
              </span>
            </button>
            <OverflowMenu
              label={`Actions for ${p.name}`}
              revealOnGroupHover
              items={[{ label: "Delete company", danger: true, onSelect: () => setDeleteTarget(p) }]}
            />
          </div>
        );})}
        {visibleProviders.length > 0 && (
          <div className="px-4 py-3 text-center">
            <p className="text-xs text-[var(--md-sys-color-on-surface-variant)]">
              Showing {visibleProviders.length} of {filtered.length} companies
            </p>
            {visibleProviders.length < filtered.length && (
              <button
                type="button"
                className="m3-show-more-button mt-2"
                onClick={() => setVisibleCount((count) => count + PROVIDER_BATCH_SIZE)}
              >
                Show {Math.min(PROVIDER_BATCH_SIZE, filtered.length - visibleProviders.length)} more companies
              </button>
            )}
          </div>
        )}
      </div>
      {deleteTarget && (
        <Modal title="Delete company" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            Delete {deleteTarget.name} and all of its policy analyses? This can’t be undone.
          </p>
          {deleteProvider.isError && (
            <p role="alert" className="mt-3 status-error">
              {deleteProvider.error instanceof Error ? deleteProvider.error.message : "The company could not be deleted."}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <MdOutlinedButton onClick={() => setDeleteTarget(null)}>Cancel</MdOutlinedButton>
            <MdFilledButton
              className="material-error"
              disabled={deleteProvider.isPending}
              onClick={() => deleteProvider.mutate(deleteTarget.id, {
                onSuccess: () => {
                  onDeleted?.(deleteTarget.id);
                  setDeleteTarget(null);
                },
              })}
            >
              {deleteProvider.isPending ? "Deleting…" : "Delete"}
            </MdFilledButton>
          </div>
        </Modal>
      )}
    </aside>
  );
}
