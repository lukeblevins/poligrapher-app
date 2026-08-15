import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import addIcon from "@material-symbols/svg-400/rounded/add.svg?url";
import arrowBackIcon from "@material-symbols/svg-400/rounded/arrow_back.svg?url";
import collectionIcon from "@material-symbols/svg-400/rounded/folder-fill.svg?url";
import analyzeIcon from "@material-symbols/svg-400/rounded/analytics.svg?url";
import scoreIcon from "@material-symbols/svg-400/rounded/checklist.svg?url";
import syncIcon from "@material-symbols/svg-400/rounded/sync.svg?url";
import verifyIcon from "@material-symbols/svg-400/rounded/verified.svg?url";
import recoverIcon from "@material-symbols/svg-400/rounded/healing.svg?url";
import closeIcon from "@material-symbols/svg-400/rounded/close.svg?url";

import { api } from "../api/client";
import type { BulkActionPreview, BulkOperation, CompanyCollection, Provider } from "../api/types";
import { useCollections, useProviders } from "../hooks/queries";
import { CompanyLogo } from "./CompanyLogo";
import { materialValue, MdCheckbox, MdFilledButton, MdFilledTextField, MdOutlinedButton, MdTextButton } from "./MaterialControls";
import { Modal } from "./Modal";
import { SelectMenu } from "./SelectMenu";

type CollectionDraft = {
  name: string;
  description: string;
  memberIds: Set<string>;
};

type BulkConfirmation = {
  operation: BulkOperation;
  collection: CompanyCollection;
  providerIds: string[];
  preview: BulkActionPreview | null;
};

export function SnackbarNotice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="m3-snackbar" role="status" aria-live="polite">
      <span>{message}</span>
      <button type="button" className="m3-snackbar-dismiss" aria-label="Dismiss notification" onClick={onDismiss}>
        <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${closeIcon}")` } as CSSProperties} aria-hidden="true" />
      </button>
    </div>
  );
}

function sourceLabel(provider: Provider) {
  if (provider.source_status === "available") return "Ready";
  if (provider.source_status === "restricted") return "Restricted";
  if (provider.source_status === "broken" || provider.source_status === "error") return "Needs attention";
  return "Source needed";
}

function sourceTone(provider: Provider) {
  if (provider.source_status === "available") return "text-[var(--md-sys-color-primary)]";
  if (provider.source_status === "restricted") return "text-[var(--md-sys-color-tertiary)]";
  if (provider.source_status === "broken" || provider.source_status === "error") return "text-[var(--md-sys-color-error)]";
  return "text-[var(--md-sys-color-on-surface-variant)]";
}

export function CollectionsWorkspace() {
  const qc = useQueryClient();
  const collectionsQuery = useCollections();
  const providersQuery = useProviders();
  const collections = collectionsQuery.data ?? [];
  const providers = providersQuery.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [visibleMemberCount, setVisibleMemberCount] = useState(100);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<CollectionDraft>({ name: "", description: "", memberIds: new Set() });
  const [draftCompanyQuery, setDraftCompanyQuery] = useState("");
  const [draftIndustry, setDraftIndustry] = useState("");
  const [draftSource, setDraftSource] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<CompanyCollection | null>(null);
  const [bulk, setBulk] = useState<BulkConfirmation | null>(null);

  const selected = collections.find((collection) => collection.id === selectedId) ?? null;
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["collections"] });
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };

  useEffect(() => {
    if (!selected || editing || creating) return;
    setDraft({
      name: selected.name,
      description: selected.description ?? "",
      memberIds: new Set(selected.provider_ids),
    });
  }, [creating, editing, selected]);

  const create = useMutation({
    mutationFn: () => api.createCollection({
      name: draft.name.trim(),
      description: draft.description.trim() || null,
      provider_ids: [...draft.memberIds],
    }),
    onSuccess: (collection) => {
      invalidate();
      setSelectedId(collection.id);
      setCreating(false);
      setEditing(false);
      setNotice("Collection created.");
    },
  });
  const update = useMutation({
    mutationFn: () => api.updateCollection(selectedId!, {
      name: draft.name.trim(),
      description: draft.description.trim() || null,
      provider_ids: [...draft.memberIds],
    }),
    onSuccess: () => {
      invalidate();
      setEditing(false);
      setNotice("Collection saved.");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      invalidate();
      setSelectedId(null);
      setConfirmDelete(null);
    },
  });
  const sync = useMutation({
    mutationFn: api.syncSp500,
    onSuccess: (summary) => {
      invalidate();
      setSelectedId(summary.collection_id);
      setNotice(`${summary.companies} current constituent companies synchronized.`);
    },
  });
  const verify = useMutation({
    mutationFn: (id: string) => api.verifyCollectionSources(id),
    onSuccess: () => {
      invalidate();
      setNotice("Source verification queued.");
    },
  });
  const recover = useMutation({
    mutationFn: (id: string) => api.recoverCollectionFailures(id),
    onSuccess: () => {
      invalidate();
      setNotice("Coverage recovery queued. Safe repairs will be kept only after analysis succeeds.");
    },
  });

  const members = useMemo(() => {
    if (!selected) return [];
    const ids = new Set(selected.provider_ids);
    const needle = query.trim().toLowerCase();
    return providers.filter((provider) =>
      ids.has(provider.id)
      && (!needle || provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle))),
    );
  }, [providers, query, selected]);
  const readyCount = selected ? providers.filter((provider) => selected.provider_ids.includes(provider.id) && provider.source_status === "available").length : 0;
  const analyzedCount = selected ? providers.filter((provider) => selected.provider_ids.includes(provider.id) && provider.analyzed_count > 0).length : 0;
  const renderedMembers = members.slice(0, visibleMemberCount);
  const pending = create.isPending || update.isPending;
  const mutationError = create.error || update.error || remove.error || sync.error || verify.error || recover.error;
  const industries = useMemo(() => [...new Set(providers.map((provider) => provider.industry).filter((industry): industry is string => Boolean(industry)))].sort(), [providers]);
  const filteredDraftProviders = useMemo(() => {
    const needle = draftCompanyQuery.trim().toLowerCase();
    return providers.filter((provider) => {
      const matchesQuery = !needle || provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle));
      const matchesIndustry = !draftIndustry || provider.industry === draftIndustry;
      const matchesSource = !draftSource
        || (draftSource === "ready" && provider.source_status === "available")
        || (draftSource === "attention" && ["restricted", "broken", "error"].includes(provider.source_status))
        || (draftSource === "missing" && !["available", "restricted", "broken", "error"].includes(provider.source_status));
      return matchesQuery && matchesIndustry && matchesSource;
    });
  }, [draftCompanyQuery, draftIndustry, draftSource, providers]);

  function beginCreate() {
    setCreating(true);
    setEditing(true);
    setSelectedId(null);
    setDraft({ name: "", description: "", memberIds: new Set() });
    setDraftCompanyQuery("");
    setDraftIndustry("");
    setDraftSource("");
    setNotice("");
  }

  function beginEdit() {
    if (!selected || selected.kind === "system") return;
    setDraft({ name: selected.name, description: selected.description ?? "", memberIds: new Set(selected.provider_ids) });
    setDraftCompanyQuery("");
    setDraftIndustry("");
    setDraftSource("");
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setCreating(false);
    if (!selectedId && collections.length) setSelectedId(collections[0].id);
  }

  useEffect(() => {
    setVisibleMemberCount(100);
  }, [query, selectedId]);

  useEffect(() => {
    if (!notice) return;
    const timeoutId = window.setTimeout(() => setNotice(""), 6000);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  function toggleDraftMember(id: string) {
    setDraft((current) => {
      const memberIds = new Set(current.memberIds);
      if (memberIds.has(id)) memberIds.delete(id);
      else memberIds.add(id);
      return { ...current, memberIds };
    });
  }

  async function previewBulk(operation: BulkOperation, collection: CompanyCollection, providerIds: string[] = []) {
    setBulk({ operation, collection, providerIds, preview: null });
    try {
      const preview = await api.previewBulkAction({
        operation,
        provider_ids: providerIds,
        collection_ids: providerIds.length ? [] : [collection.id],
      });
      setBulk({ operation, collection, providerIds, preview });
    } catch (error) {
      setBulk(null);
      setNotice(error instanceof Error ? error.message : "Could not preview this operation.");
    }
  }

  async function queueBulk() {
    if (!bulk?.preview) return;
    await api.runBulkAction({
      operation: bulk.operation,
      provider_ids: bulk.providerIds,
      collection_ids: bulk.providerIds.length ? [] : [bulk.collection.id],
    });
    invalidate();
    setBulk(null);
    setNotice("Bulk task queued.");
  }

  return (
    <main className="flex min-h-0 flex-1 overflow-hidden">
      <aside
        aria-label="Collection browser"
        className={`${selected || creating ? "hidden lg:flex" : "flex"} m3-list-detail-pane ui-subtle w-full flex-shrink-0 flex-col sm:w-[calc(100%-1rem)] lg:w-[clamp(20rem,26vw,24rem)]`}
      >
        <div className="px-4 py-4">
          <div className="m3-mobile-redundant-title flex items-center justify-between gap-3">
            <h1 className="m3-workspace-title">Collections</h1>
            <span className="m3-count-badge data-value">{collections.length}</span>
          </div>
          <button type="button" className="m3-collection-create-action mt-4" onClick={beginCreate}>
            <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${addIcon}")` } as CSSProperties} aria-hidden="true" />
            <span>New collection</span>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {collectionsQuery.isLoading && <p role="status" className="m-4 quiet-state">Loading collections…</p>}
          {collectionsQuery.isError && <p role="alert" className="m-4 status-error">Could not load collections.</p>}
          {!collectionsQuery.isLoading && !collectionsQuery.isError && collections.length === 0 && (
            <p className="m-4 quiet-state">Create a collection to organize and analyze companies together.</p>
          )}
          {collections.map((collection) => (
            <button
              key={collection.id}
              type="button"
              className={`m3-navigation-item m3-collection-list-item ${
                selectedId === collection.id
                  ? "m3-navigation-item-selected"
                  : ""
              }`}
              aria-current={selectedId === collection.id ? "true" : undefined}
              onClick={() => { setSelectedId(collection.id); setCreating(false); setEditing(false); setNotice(""); }}
            >
              <span className="m3-collection-list-icon"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${collectionIcon}")` } as CSSProperties} aria-hidden="true" /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-base font-medium">{collection.name}</span>
                <span className="m3-collection-list-meta">
                  <span className="data-value">{collection.provider_count}</span> {collection.provider_count === 1 ? "company" : "companies"}
                  {collection.kind === "system" ? <span className="m3-collection-managed-label">Managed</span> : null}
                </span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      <section className={`${!selected && !creating ? "hidden lg:flex" : "flex"} m3-detail-pane min-w-0 flex-1 flex-col overflow-y-auto`}>
        <div className="mx-auto w-full max-w-[76rem] px-4 py-4 sm:px-5 sm:py-5 lg:px-6">
          <button type="button" className="m3-mobile-content-back mb-3 lg:hidden" aria-label="Back to collections" onClick={() => { setSelectedId(null); setCreating(false); }}>
            <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${arrowBackIcon}")` } as CSSProperties} aria-hidden="true" />
          </button>
          {editing || creating ? (
            <div className="m3-collection-editor w-full">
              <header className="m3-collection-editor-header">
                <h1 className="font-display text-3xl font-medium text-[var(--md-sys-color-on-surface)]">{creating ? "Create a collection" : `Edit ${selected?.name}`}</h1>
              </header>
              <div className="m3-collection-editor-fields">
                <MdFilledTextField id="collection-name" className="w-full" label="Collection name" value={draft.name} onInput={(event) => setDraft((current) => ({ ...current, name: materialValue(event) }))} />
                <MdFilledTextField id="collection-note" className="w-full" type="textarea" rows={3} label="Note (optional)" value={draft.description} onInput={(event) => setDraft((current) => ({ ...current, description: materialValue(event) }))} />
              </div>
              <fieldset className="m3-collection-member-picker">
                <div className="m3-collection-member-heading">
                  <div>
                    <legend className="font-display text-xl font-medium">Companies</legend>
                    <p className="mt-1 text-sm text-[var(--md-sys-color-on-surface-variant)]"><span className="data-value">{draft.memberIds.size}</span> selected, <span className="data-value">{filteredDraftProviders.length}</span> shown</p>
                  </div>
                  <div className="m3-collection-selection-actions">
                    <MdTextButton onClick={() => setDraft((current) => ({ ...current, memberIds: new Set([...current.memberIds, ...filteredDraftProviders.map((provider) => provider.id)]) }))}>Select all</MdTextButton>
                    <MdTextButton onClick={() => setDraft((current) => {
                      const memberIds = new Set(current.memberIds);
                      filteredDraftProviders.forEach((provider) => memberIds.delete(provider.id));
                      return { ...current, memberIds };
                    })}>Clear</MdTextButton>
                  </div>
                </div>
                <div className="m3-collection-filter-grid">
                  <MdFilledTextField className="m3-collection-filter-search w-full" label="Search companies" value={draftCompanyQuery} onInput={(event) => setDraftCompanyQuery(materialValue(event))} />
                  <SelectMenu className="w-full" label="Industry" value={draftIndustry} onChange={setDraftIndustry} options={[{ value: "", label: "All industries" }, ...industries.map((industry) => ({ value: industry, label: industry }))]} />
                  <SelectMenu className="w-full" label="Policy source" value={draftSource} onChange={setDraftSource} options={[
                    { value: "", label: "All source states" },
                    { value: "ready", label: "Ready" },
                    { value: "attention", label: "Needs attention" },
                    { value: "missing", label: "Source needed" },
                  ]} />
                </div>
                <div className="m3-list m3-collection-company-picker max-h-[24rem] overflow-y-auto">
                    {filteredDraftProviders.map((provider) => (
                      <label key={provider.id} className="m3-list-item flex cursor-pointer items-center gap-3 px-3 py-2">
                        <MdCheckbox checked={draft.memberIds.has(provider.id)} onChange={() => toggleDraftMember(provider.id)} />
                        <CompanyLogo name={provider.name} domain={provider.domain} className="h-7 w-7" />
                        <span className="min-w-0 flex-1 truncate text-sm font-medium">{provider.name}</span>
                        <span className="data-value text-xs text-[var(--md-sys-color-on-surface-variant)]">{provider.tickers.join(", ")}</span>
                      </label>
                    ))}
                    {filteredDraftProviders.length === 0 ? <p className="m3-scheduled-empty">No companies match these filters.</p> : null}
                  </div>
              </fieldset>
              {(create.isError || update.isError) && <p role="alert" className="mt-4 status-error">{mutationError instanceof Error ? mutationError.message : "Could not save the collection."}</p>}
              <div className="m3-collection-editor-actions">
                <MdOutlinedButton onClick={cancelEdit}>Cancel</MdOutlinedButton>
                <MdFilledButton disabled={pending || !draft.name.trim()} onClick={() => creating ? create.mutate() : update.mutate()}>
                  {pending ? "Saving…" : creating ? "Create collection" : "Save changes"}
                </MdFilledButton>
              </div>
            </div>
          ) : selected ? (
            <>
              <header>
                <div className="grid gap-5">
                  <div>
                    <p className="section-kicker">{selected.kind === "system" ? "Managed index" : "Research collection"}</p>
                    <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight text-[var(--md-sys-color-on-surface)] sm:text-4xl">{selected.name}</h1>
                    <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">{selected.description || "No collection description."}</p>
                  </div>
                  <div className="m3-collection-action-group" role="group" aria-label="Collection actions">
                    <button type="button" onClick={() => previewBulk("generate", selected)}><span className="m3-button-label"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${analyzeIcon}")` } as CSSProperties} aria-hidden="true" />Analyze</span></button>
                    <button type="button" disabled={verify.isPending} onClick={() => verify.mutate(selected.id)}><span className="m3-button-label"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${verifyIcon}")` } as CSSProperties} aria-hidden="true" />{verify.isPending ? "Queueing…" : "Verify"}</span></button>
                    <button type="button" disabled={recover.isPending} onClick={() => recover.mutate(selected.id)}><span className="m3-button-label"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${recoverIcon}")` } as CSSProperties} aria-hidden="true" />{recover.isPending ? "Queueing…" : "Recover"}</span></button>
                    <button type="button" onClick={() => previewBulk("score", selected)}><span className="m3-button-label"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${scoreIcon}")` } as CSSProperties} aria-hidden="true" />Score</span></button>
                    {selected.kind === "system" && <button type="button" disabled={sync.isPending} onClick={() => sync.mutate()}><span className="m3-button-label"><span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${syncIcon}")` } as CSSProperties} aria-hidden="true" />{sync.isPending ? "Syncing…" : "Sync"}</span></button>}
                  </div>
                </div>
                <dl className="mt-7 grid grid-cols-2 gap-x-6 gap-y-4 pt-1 sm:grid-cols-4">
                  <div><dt className="section-kicker">Companies</dt><dd className="data-value mt-1 text-xl font-semibold">{selected.provider_count}</dd></div>
                  <div><dt className="section-kicker">Sources ready</dt><dd className="data-value mt-1 text-xl font-semibold">{readyCount}</dd></div>
                  <div><dt className="section-kicker">Analyzed</dt><dd className="data-value mt-1 text-xl font-semibold">{analyzedCount}</dd></div>
                  <div><dt className="section-kicker">Snapshot</dt><dd className="data-value mt-1 text-sm font-semibold">{selected.snapshot_date ?? "Not applicable"}</dd></div>
                </dl>
              </header>

              {mutationError && <p role="alert" className="mt-5 status-error">{mutationError instanceof Error ? mutationError.message : "The action could not be completed."}</p>}

              <section className="mt-6" aria-labelledby="collection-members-heading">
                <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
                  <div>
                    <h2 id="collection-members-heading" className="font-display text-2xl font-semibold">Companies</h2>
                    <p className="mt-1 text-sm text-[var(--md-sys-color-on-surface-variant)]">Review source readiness and analysis coverage across this cohort.</p>
                  </div>
                  <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
                    <label className="m3-contained-search w-full lg:w-64">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>
                      <input id="collection-member-search" type="search" placeholder="Search companies" value={query} onChange={(event) => setQuery(event.target.value)} />
                    </label>
                    {selected.kind !== "system" && <MdOutlinedButton onClick={beginEdit}>Edit members</MdOutlinedButton>}
                  </div>
                </div>
                <div className="m3-list mt-4">
                  {providersQuery.isError && <p role="alert" className="m-4 status-error">Could not load companies.</p>}
                  {members.length === 0 && !providersQuery.isError && <p className="quiet-state my-4">No companies match this search.</p>}
                  {renderedMembers.map((provider) => (
                    <div key={provider.id} className="m3-list-item grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_10rem_9rem]">
                      <div className="flex min-w-0 items-center gap-3">
                        <CompanyLogo name={provider.name} domain={provider.domain} className="h-8 w-8" />
                        <div className="min-w-0"><p className="truncate text-sm font-semibold">{provider.name}</p><p className="truncate text-xs text-[var(--md-sys-color-on-surface-variant)]">{provider.tickers.join(", ") || provider.industry || "Uncategorized"}</p></div>
                      </div>
                      <p className={`text-xs font-semibold ${sourceTone(provider)}`}>{sourceLabel(provider)}</p>
                      <p className="data-value hidden text-right text-xs text-[var(--md-sys-color-on-surface-variant)] sm:block">{provider.policy_count} {provider.policy_count === 1 ? "analysis" : "analyses"}</p>
                    </div>
                  ))}
                </div>
                {renderedMembers.length < members.length && (
                  <button className="m3-show-more-button mt-3" onClick={() => setVisibleMemberCount((count) => count + 100)}>
                    Show {Math.min(100, members.length - renderedMembers.length)} more companies
                  </button>
                )}
              </section>

              {selected.kind !== "system" && (
                <div className="mt-10 flex justify-between pt-5">
                  <button className="min-h-11 text-sm font-semibold text-[var(--md-sys-color-error)] hover:underline" onClick={() => setConfirmDelete(selected)}>Delete collection</button>
                  <MdOutlinedButton onClick={beginEdit}>Edit collection</MdOutlinedButton>
                </div>
              )}
            </>
          ) : (
            <div className="m3-collection-empty-state flex items-center justify-center p-6 text-[var(--md-sys-color-on-surface-variant)]">
              <div className="m3-empty-state text-center">
                <p className="font-display text-2xl font-semibold text-[var(--md-sys-color-on-surface)]">Select a collection</p>
                <p className="mt-2 text-sm leading-6">Review its companies and run collection-wide analyses.</p>
              </div>
            </div>
          )}
        </div>
      </section>

      {bulk && (
        <Modal title={`${bulk.operation === "generate" ? "Generate analyses" : "Score analyses"}: ${bulk.collection.name}`} onClose={() => setBulk(null)}>
          {!bulk.preview ? (
            <p role="status" className="quiet-state">Calculating eligible work…</p>
          ) : (
            <>
              <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
                {bulk.operation === "generate"
                  ? `Analyze ${bulk.preview.eligible_count} ${bulk.preview.eligible_count === 1 ? "company" : "companies"} that do not have completed graph output.`
                  : `Score ${bulk.preview.eligible_count} eligible ${bulk.preview.eligible_count === 1 ? "policy" : "policies"} across ${bulk.preview.provider_count} ${bulk.preview.provider_count === 1 ? "company" : "companies"}.`}
                {bulk.preview.skipped_count > 0 ? ` ${bulk.preview.skipped_count} companies are already complete or do not have a policy source.` : ""}
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <MdOutlinedButton onClick={() => setBulk(null)}>Cancel</MdOutlinedButton>
                <MdFilledButton disabled={bulk.preview.eligible_count === 0} onClick={queueBulk}>Confirm and queue</MdFilledButton>
              </div>
            </>
          )}
        </Modal>
      )}

      {confirmDelete && (
        <Modal title="Delete collection" onClose={() => setConfirmDelete(null)}>
          <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">Delete {confirmDelete.name}? Its companies and analyses will remain in the workspace.</p>
          <div className="mt-5 flex justify-end gap-2">
            <MdOutlinedButton onClick={() => setConfirmDelete(null)}>Cancel</MdOutlinedButton>
            <MdFilledButton className="material-error" disabled={remove.isPending} onClick={() => remove.mutate(confirmDelete.id)}>{remove.isPending ? "Deleting…" : "Delete collection"}</MdFilledButton>
          </div>
        </Modal>
      )}

      {notice && <SnackbarNotice message={notice} onDismiss={() => setNotice("")} />}
    </main>
  );
}
