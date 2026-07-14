import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { CompanyCatalogResult, Provider } from "../../api/types";
import { useCreateProvider } from "../../hooks/queries";
import { CompanyLogo } from "../CompanyLogo";
import { Modal } from "../Modal";

type Mode = "search" | "manual";

function domainFromWebsite(value: string): string | null {
  const candidate = value.trim();
  if (!candidate) return null;
  try {
    const url = new URL(candidate.includes("://") ? candidate : `https://${candidate}`);
    return url.hostname.replace(/^www\./, "").toLowerCase() || null;
  } catch {
    return null;
  }
}

export function AddProviderModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (provider: Provider) => void;
}) {
  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selected, setSelected] = useState<CompanyCatalogResult | null>(null);
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [policyUrl, setPolicyUrl] = useState("");
  const [industry, setIndustry] = useState("");
  const createProvider = useCreateProvider();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const catalog = useQuery({
    queryKey: ["company-catalog", debouncedQuery],
    queryFn: () => api.searchCompanyCatalog(debouncedQuery),
    enabled: mode === "search" && debouncedQuery.length >= 2,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  async function create(body: {
    name: string;
    industry: string | null;
    domain?: string | null;
    source_url?: string | null;
  }) {
    try {
      const created = await createProvider.mutateAsync(body);
      onCreated?.(created);
      onClose();
    } catch {
      /* error surfaced below */
    }
  }

  function submitSelected(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    void create({
      name: selected.name,
      industry: industry.trim() || null,
      domain: selected.domain,
      source_url: selected.source_url,
    });
  }

  function submitManual(event: React.FormEvent) {
    event.preventDefault();
    const domain = domainFromWebsite(website);
    if (!domain) return;
    void create({
      name: name.trim(),
      industry: industry.trim() || null,
      domain,
      source_url: policyUrl.trim() || null,
    });
  }

  return (
    <Modal title="Add company" onClose={onClose} wide>
      <div className="mb-5 flex border-b border-slate-300 dark:border-slate-700">
        <button
          className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "search" ? "border-teal-700 text-teal-800 dark:border-teal-400 dark:text-teal-300" : "border-transparent text-slate-500 dark:text-slate-400"}`}
          onClick={() => setMode("search")}
        >
          Search tracked companies
        </button>
        <button
          className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "manual" ? "border-teal-700 text-teal-800 dark:border-teal-400 dark:text-teal-300" : "border-transparent text-slate-500 dark:text-slate-400"}`}
          onClick={() => setMode("manual")}
        >
          Use company website
        </button>
      </div>

      {mode === "search" ? (
        selected ? (
          <form onSubmit={submitSelected} className="space-y-4">
            <button type="button" className="text-xs font-semibold text-teal-700 hover:underline dark:text-teal-400" onClick={() => setSelected(null)}>
              ← Back to results
            </button>
            <div className="rounded-md border border-teal-300 bg-teal-50/50 p-4 dark:border-teal-900 dark:bg-teal-950/25">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <CompanyLogo name={selected.name} domain={selected.domain} className="h-10 w-10" />
                  <div>
                  <h3 className="font-display text-lg font-bold">{selected.name}</h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{selected.domain}</p>
                  </div>
                </div>
                <span className="bg-teal-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-teal-800 dark:bg-teal-900 dark:text-teal-200">Open Terms Archive</span>
              </div>
              <p className="mt-3 break-all text-xs leading-5 text-slate-600 dark:text-slate-300">{selected.source_url}</p>
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                The maintained policy URL and extraction metadata will be used as the starting source.
              </p>
            </div>
            <div>
              <label className="form-label" htmlFor="catalog-industry">Industry (optional)</label>
              <input id="catalog-industry" className="form-input" value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder="e.g. Healthcare" />
            </div>
            {createProvider.isError && <p className="text-xs text-red-600 dark:text-red-400">{(createProvider.error as Error).message}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={createProvider.isPending}>{createProvider.isPending ? "Adding…" : "Add company"}</button>
            </div>
          </form>
        ) : (
          <div>
            <p className="mb-4 text-sm leading-6 text-slate-600 dark:text-slate-400">
              Start with a company already tracked by Open Terms Archive. Matching records include a maintained privacy-policy source.
            </p>
            <label className="form-label" htmlFor="company-catalog-search">Company or service name</label>
            <input id="company-catalog-search" className="form-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search GitHub, Microsoft, YouTube…" autoFocus />
            <div className="mt-3 min-h-28">
              {catalog.isFetching && <p className="quiet-state py-6">Searching Open Terms Archive…</p>}
              {catalog.data && !catalog.data.source_available && (
                <p className="quiet-state py-6">The public catalog is temporarily unavailable. You can still add this company manually.</p>
              )}
              {catalog.data?.source_available && catalog.data.results.length === 0 && debouncedQuery.length >= 2 && !catalog.isFetching && (
                <p className="quiet-state py-6">No tracked privacy policy matched “{debouncedQuery}”. Try another name or add the company manually.</p>
              )}
              {catalog.data && catalog.data.results.length > 0 && (
                <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-300 dark:divide-slate-800 dark:border-slate-700">
                  {catalog.data.results.map((result) => (
                    <button key={result.id} className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => setSelected(result)}>
                      <CompanyLogo name={result.name} domain={result.domain} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold">{result.name}</span>
                        <span className="mt-0.5 block truncate text-xs text-slate-500 dark:text-slate-400">{result.domain} · Privacy policy tracked</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="mt-4 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400 dark:border-slate-800">
              Not every company is represented in the open catalog. Choose “Use company website” for an organization that is not listed.
            </p>
          </div>
        )
      ) : (
        <form onSubmit={submitManual} className="space-y-4">
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-400">
            Add any organization by its public website. The application can then look for a privacy-policy source on that domain.
          </p>
          <div>
            <label className="form-label" htmlFor="manual-company-name">Company name</label>
            <input id="manual-company-name" className="form-input" value={name} onChange={(event) => setName(event.target.value)} required autoFocus />
          </div>
          <div>
            <label className="form-label" htmlFor="manual-company-website">Company website</label>
            <input id="manual-company-website" className="form-input" value={website} onChange={(event) => setWebsite(event.target.value)} placeholder="example.com" required />
            {website && !domainFromWebsite(website) && <p className="mt-1.5 text-xs text-red-500">Enter a valid website or domain.</p>}
          </div>
          <details className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700">
            <summary className="cursor-pointer text-xs font-semibold">Optional details</summary>
            <div className="mt-3 space-y-3">
              <div>
                <label className="form-label" htmlFor="manual-policy-url">Known privacy-policy URL</label>
                <input id="manual-policy-url" className="form-input" value={policyUrl} onChange={(event) => setPolicyUrl(event.target.value)} placeholder="https://example.com/privacy" />
              </div>
              <div>
                <label className="form-label" htmlFor="manual-industry">Industry</label>
                <input id="manual-industry" className="form-input" value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder="e.g. Financial services" />
              </div>
            </div>
          </details>
          {createProvider.isError && <p className="text-xs text-red-600 dark:text-red-400">{(createProvider.error as Error).message}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createProvider.isPending || !name.trim() || !domainFromWebsite(website)}>{createProvider.isPending ? "Adding…" : "Add company"}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
