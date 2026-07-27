import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { CompanyCatalogResult, Provider } from "../../api/types";
import { useCreateProvider } from "../../hooks/queries";
import { CompanyLogo } from "../CompanyLogo";
import { materialValue, MdFilledButton, MdOutlinedButton, MdOutlinedTextField, MdTextButton } from "../MaterialControls";
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
  const websiteInvalid = Boolean(website) && !domainFromWebsite(website);

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
      <div role="group" aria-label="Company source" className="mb-5 flex overflow-x-auto border-b border-slate-300 dark:border-slate-700">
        <button
          type="button"
          aria-pressed={mode === "search"}
          className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "search" ? "border-teal-700 text-teal-800 dark:border-teal-400 dark:text-teal-300" : "border-transparent text-slate-500 dark:text-slate-400"}`}
          onClick={() => setMode("search")}
        >
          Search tracked companies
        </button>
        <button
          type="button"
          aria-pressed={mode === "manual"}
          className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "manual" ? "border-teal-700 text-teal-800 dark:border-teal-400 dark:text-teal-300" : "border-transparent text-slate-500 dark:text-slate-400"}`}
          onClick={() => setMode("manual")}
        >
          Use company website
        </button>
      </div>

      {mode === "search" ? (
        selected ? (
          <form onSubmit={submitSelected} className="space-y-4">
            <MdTextButton type="button" onClick={() => setSelected(null)}>
              ← Back to results
            </MdTextButton>
            <div className="rounded-[var(--md-sys-shape-corner-medium)] border border-[var(--md-sys-color-outline-variant)] bg-[var(--md-sys-color-primary-container)] p-4 text-[var(--md-sys-color-on-primary-container)]">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <CompanyLogo name={selected.name} domain={selected.domain} className="h-10 w-10" />
                  <div>
                  <h3 className="font-display text-lg font-bold">{selected.name}</h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{selected.domain}</p>
                  </div>
                </div>
                <span className="rounded-full bg-[var(--md-sys-color-surface-container-highest)] px-3 py-1 text-[11px] font-medium text-[var(--md-sys-color-on-surface)]">Open Terms Archive</span>
              </div>
              <p className="mt-3 break-all text-xs leading-5 text-slate-600 dark:text-slate-300">{selected.source_url}</p>
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                The maintained policy URL and extraction metadata will be used as the starting source.
              </p>
            </div>
            <MdOutlinedTextField id="catalog-industry" className="w-full" label="Industry (optional)" value={industry} onInput={(event) => setIndustry(materialValue(event))} placeholder="e.g. Healthcare" />
            {createProvider.isError && <p role="alert" className="status-error">{(createProvider.error as Error).message}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <MdOutlinedButton type="button" onClick={onClose}>Cancel</MdOutlinedButton>
              <MdFilledButton type="submit" disabled={createProvider.isPending}>{createProvider.isPending ? "Adding…" : "Add company"}</MdFilledButton>
            </div>
          </form>
        ) : (
          <div>
            <p className="mb-4 text-sm leading-6 text-slate-600 dark:text-slate-400">
              Start with a company already tracked by Open Terms Archive. Matching records include a maintained privacy-policy source.
            </p>
            <MdOutlinedTextField id="company-catalog-search" type="search" className="w-full" label="Company or service name" value={query} onInput={(event) => setQuery(materialValue(event))} placeholder="Search GitHub, Microsoft, YouTube…" />
            <div className="mt-3 min-h-28">
              {catalog.isFetching && <p role="status" className="quiet-state py-6">Searching Open Terms Archive…</p>}
              {catalog.isError && !catalog.isFetching && (
                <p role="alert" className="status-error">Company search is unavailable. Try again or use the company website option.</p>
              )}
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
            <p className="mt-4 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500 dark:border-slate-800 dark:text-slate-400">
              Not every company is represented in the open catalog. Choose “Use company website” for an organization that is not listed.
            </p>
          </div>
        )
      ) : (
        <form onSubmit={submitManual} className="space-y-4">
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-400">
            Add any organization by its public website. The application can then look for a privacy-policy source on that domain.
          </p>
          <MdOutlinedTextField
              id="manual-company-name"
              className="w-full"
              label="Company name"
              value={name}
              onInput={(event) => setName(materialValue(event))}
              required
          />
          <div>
            <MdOutlinedTextField
              id="manual-company-website"
              className="w-full"
              label="Company website"
              value={website}
              onInput={(event) => setWebsite(materialValue(event))}
              placeholder="example.com"
              error={websiteInvalid}
              errorText="Enter a valid website or domain."
              aria-describedby="manual-company-website-error"
              required
            />
            {websiteInvalid && <p id="manual-company-website-error" className="mt-1.5 text-xs text-red-600 dark:text-red-400">Enter a valid website or domain.</p>}
          </div>
          <details className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700">
            <summary className="cursor-pointer text-xs font-semibold">Optional details</summary>
            <div className="mt-3 space-y-3">
              <div>
                <MdOutlinedTextField id="manual-policy-url" className="w-full" type="url" label="Known privacy-policy URL" value={policyUrl} onInput={(event) => setPolicyUrl(materialValue(event))} placeholder="https://example.com/privacy" />
              </div>
              <div>
                <MdOutlinedTextField id="manual-industry" className="w-full" label="Industry" value={industry} onInput={(event) => setIndustry(materialValue(event))} placeholder="e.g. Financial services" />
              </div>
            </div>
          </details>
          {createProvider.isError && <p role="alert" className="status-error">{(createProvider.error as Error).message}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <MdOutlinedButton type="button" onClick={onClose}>Cancel</MdOutlinedButton>
            <MdFilledButton type="submit" disabled={createProvider.isPending || !name.trim() || !domainFromWebsite(website)}>{createProvider.isPending ? "Adding…" : "Add company"}</MdFilledButton>
          </div>
        </form>
      )}
    </Modal>
  );
}
