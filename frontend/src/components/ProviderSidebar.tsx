import { useState } from "react";

import type { Provider } from "../api/types";
import { useCollections, useDeleteProvider, useProviders } from "../hooks/queries";
import { CompanyLogo } from "./CompanyLogo";

interface Props {
  selectedId: string | null;
  onSelect: (provider: Provider) => void;
  onDeleted?: (id: string) => void;
}

function statusColor(p: Provider): string {
  if (p.policy_count === 0) return "bg-zinc-300 dark:bg-zinc-600";
  if (p.succeeded_count > 0) return "bg-green-500";
  if (p.failed_count === p.policy_count) return "bg-red-500";
  return "bg-amber-400";
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
  const [industry, setIndustry] = useState("all");

  const selectedCollection = collections.find((collection) => collection.id === collectionId);
  const collectionMembers = selectedCollection ? new Set(selectedCollection.provider_ids) : null;
  const industries = [...new Set(providers.map((provider) => provider.industry).filter((value): value is string => !!value))].sort();
  const needle = query.toLowerCase();
  const filtered = providers.filter((provider) =>
    (!collectionMembers || collectionMembers.has(provider.id))
    && (industry === "all" || provider.industry === industry)
    && (provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle))),
  );

  return (
    <aside className="flex w-72 flex-shrink-0 flex-col border-r border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="border-b border-slate-100 px-4 py-4 dark:border-slate-800">
        <div className="mb-2.5 flex items-center justify-between px-0.5">
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">Companies</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">{filtered.length}</span>
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
          <label>
            <span className="sr-only">Industry</span>
            <select className="form-input py-1.5 text-xs" value={industry} onChange={(event) => setIndustry(event.target.value)}>
              <option value="all">All industries</option>
              {industries.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-sm text-slate-400">Loading…</p>}
        {!isLoading && filtered.length === 0 && (
          <p className="p-4 text-sm text-slate-400">No companies.</p>
        )}
        {filtered.map((p) => (
          <div
            key={p.id}
            onClick={() => onSelect(p)}
            className={`group flex cursor-pointer items-center gap-3 border-l-2 px-4 py-3 text-sm transition-colors ${
              selectedId === p.id
                ? "border-teal-600 bg-teal-50/70 font-semibold text-slate-950 dark:border-teal-400 dark:bg-teal-950/30 dark:text-white"
                : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-900"
            }`}
          >
            <span className="relative flex-shrink-0">
              <CompanyLogo name={p.name} domain={logoDomain(p)} />
              <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white dark:border-slate-950 ${statusColor(p)}`} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate">{p.name}</div>
              <div className="mt-0.5 truncate text-xs text-slate-400 dark:text-slate-500">
                {p.ticker ? `${p.ticker} · ` : ""}{p.industry ?? "Uncategorized"} · {p.policy_count} results
              </div>
            </div>
            {p.source_status !== "available" && p.source_status !== "unchecked" && (
              <span
                className={`h-2 w-2 flex-none rounded-full ${p.source_status === "broken" || p.source_status === "error" ? "bg-red-500" : p.source_status === "restricted" ? "bg-amber-400" : "bg-slate-300 dark:bg-slate-600"}`}
                title={`Policy source: ${p.source_status}`}
              />
            )}
            <button
              className="hidden rounded-md px-1.5 py-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600 group-hover:block dark:hover:bg-red-950"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete provider "${p.name}" and all its policies?`)) {
                  deleteProvider.mutate(p.id, {
                    onSuccess: () => onDeleted?.(p.id),
                  });
                }
              }}
              aria-label={`Delete ${p.name}`}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
