import { useQuery } from "@tanstack/react-query";
import arrowBackIcon from "@material-symbols/svg-400/rounded/arrow_back.svg?url";
import arrowForwardIcon from "@material-symbols/svg-400/rounded/arrow_forward.svg?url";
import expandMoreIcon from "@material-symbols/svg-400/rounded/keyboard_arrow_down.svg?url";
import languageIcon from "@material-symbols/svg-400/rounded/language.svg?url";
import searchIcon from "@material-symbols/svg-400/rounded/search.svg?url";
import { useEffect, useState, type CSSProperties } from "react";

import { api } from "../../api/client";
import type { CompanyCatalogResult, Provider } from "../../api/types";
import { useCreateProvider } from "../../hooks/queries";
import { CompanyLogo } from "../CompanyLogo";
import { materialValue, MdFilledButton, MdFilledTextField, MdTextButton } from "../MaterialControls";
import { Modal } from "../Modal";

type Mode = "search" | "manual";

function MaterialIcon({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

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
    <Modal title="Add company" onClose={onClose} wide className="add-company-dialog" showCloseButton={false}>
      <div role="tablist" aria-label="How to add a company" className="add-company-tabs">
        <button
          type="button"
          role="tab"
          id="company-source-search"
          aria-selected={mode === "search"}
          aria-controls="company-source-panel"
          className="add-company-tab"
          onClick={() => setMode("search")}
        >
          <span className="add-company-tab-icon"><MaterialIcon src={searchIcon} /></span>
          Search companies
        </button>
        <button
          type="button"
          role="tab"
          id="company-source-manual"
          aria-selected={mode === "manual"}
          aria-controls="company-source-panel"
          className="add-company-tab"
          onClick={() => setMode("manual")}
        >
          <span className="add-company-tab-icon"><MaterialIcon src={languageIcon} /></span>
          Add by website
        </button>
      </div>

      <div
        id="company-source-panel"
        role="tabpanel"
        aria-labelledby={mode === "search" ? "company-source-search" : "company-source-manual"}
        className="add-company-panel"
      >
      {mode === "search" ? (
        selected ? (
          <form onSubmit={submitSelected} className="space-y-4">
            <MdTextButton type="button" className="add-company-back" onClick={() => setSelected(null)}>
              <MaterialIcon src={arrowBackIcon} /> Back to results
            </MdTextButton>
            <div className="add-company-selection">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <CompanyLogo name={selected.name} domain={selected.domain} className="h-10 w-10" />
                  <div>
                    <h3 className="font-display text-lg font-bold">{selected.name}</h3>
                    <p className="add-company-domain">{selected.domain}</p>
                  </div>
                </div>
                <span className="add-company-badge">Policy tracked</span>
              </div>
              <p className="add-company-source">{selected.source_url}</p>
              <p className="add-company-supporting">
                We’ll use this tracked policy as the starting point for analysis.
              </p>
            </div>
            <MdFilledTextField id="catalog-industry" className="w-full" label="Industry (optional)" value={industry} onInput={(event) => setIndustry(materialValue(event))} placeholder="e.g. Healthcare" />
            {createProvider.isError && <p role="alert" className="status-error">{(createProvider.error as Error).message}</p>}
            <div className="add-company-actions">
              <MdTextButton type="button" onClick={onClose}>Cancel</MdTextButton>
              <MdFilledButton type="submit" disabled={createProvider.isPending}>{createProvider.isPending ? "Adding…" : "Add company"}</MdFilledButton>
            </div>
          </form>
        ) : (
          <div className="add-company-flow">
            <MdFilledTextField id="company-catalog-search" type="search" className="w-full" label="Company name" value={query} onInput={(event) => setQuery(materialValue(event))} placeholder="GitHub, Microsoft, YouTube…" />
            <div className="add-company-results" aria-live="polite">
              {catalog.isFetching && <p role="status" className="quiet-state py-6">Searching Open Terms Archive…</p>}
              {catalog.isError && !catalog.isFetching && (
                <p role="alert" className="status-error">Company search is unavailable. Try again or add the company by website.</p>
              )}
              {catalog.data && !catalog.data.source_available && (
                <p className="quiet-state py-6">The company catalog is temporarily unavailable. You can still add the company by website.</p>
              )}
              {catalog.data?.source_available && catalog.data.results.length === 0 && debouncedQuery.length >= 2 && !catalog.isFetching && (
                <p className="quiet-state py-6">No tracked company matched “{debouncedQuery}”. Try another name or add it by website.</p>
              )}
              {catalog.data && catalog.data.results.length > 0 && (
                <div className="add-company-result-list">
                  {catalog.data.results.map((result) => (
                    <button key={result.id} className="add-company-result" onClick={() => setSelected(result)}>
                      <CompanyLogo name={result.name} domain={result.domain} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold">{result.name}</span>
                        <span className="add-company-domain block truncate">{result.domain} — policy tracked</span>
                      </span>
                      <span className="add-company-result-arrow"><MaterialIcon src={arrowForwardIcon} /></span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      ) : (
        <form onSubmit={submitManual} className="add-company-flow">
          <div className="add-company-fields">
          <MdFilledTextField
              id="manual-company-name"
              className="w-full"
              label="Company name"
              value={name}
              onInput={(event) => setName(materialValue(event))}
              required
          />
          <MdFilledTextField
              id="manual-company-website"
              className="w-full"
              label="Company website"
              value={website}
              onInput={(event) => setWebsite(materialValue(event))}
              placeholder="example.com"
              error={websiteInvalid}
              errorText="Enter a valid website or domain."
              required
            />
          </div>
          <details className="add-company-details">
            <summary>
              <span>Optional details</span>
              <span className="add-company-details-chevron"><MaterialIcon src={expandMoreIcon} /></span>
            </summary>
            <div className="add-company-details-fields">
              <MdFilledTextField id="manual-policy-url" className="w-full" type="url" label="Privacy policy URL" value={policyUrl} onInput={(event) => setPolicyUrl(materialValue(event))} placeholder="https://example.com/privacy" />
              <MdFilledTextField id="manual-industry" className="w-full" label="Industry" value={industry} onInput={(event) => setIndustry(materialValue(event))} placeholder="e.g. Financial services" />
            </div>
          </details>
          {createProvider.isError && <p role="alert" className="status-error">{(createProvider.error as Error).message}</p>}
          <div className="add-company-actions">
            <MdTextButton type="button" onClick={onClose}>Cancel</MdTextButton>
            <MdFilledButton type="submit" disabled={createProvider.isPending || !name.trim() || !domainFromWebsite(website)}>{createProvider.isPending ? "Adding…" : "Add company"}</MdFilledButton>
          </div>
        </form>
      )}
      </div>
    </Modal>
  );
}
