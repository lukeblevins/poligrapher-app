import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import { useCollections, useProviders } from "../../hooks/queries";
import { useTaskRunner } from "../../hooks/useTaskRunner";
import { CompanyLogo } from "../CompanyLogo";
import { Modal } from "../Modal";

export function CollectionsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: providers = [] } = useProviders();
  const { data: collections = [], isLoading } = useCollections();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [memberIds, setMemberIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");

  const selected = creating ? null : collections.find((collection) => collection.id === selectedId) ?? null;
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["collections"] });
    qc.invalidateQueries({ queryKey: ["providers"] });
  };
  const { start } = useTaskRunner(invalidate);

  useEffect(() => {
    if (!selectedId && !creating && collections.length) setSelectedId(collections[0].id);
  }, [collections, selectedId, creating]);

  useEffect(() => {
    if (!selected) return;
    setName(selected.name);
    setDescription(selected.description ?? "");
    setMemberIds(new Set(selected.provider_ids));
    setNotice("");
  }, [selected]);

  const create = useMutation({
    mutationFn: () => api.createCollection({ name: name.trim(), description: description.trim() || null, provider_ids: [...memberIds] }),
    onSuccess: (collection) => {
      invalidate();
      setCreating(false);
      setSelectedId(collection.id);
      setNotice("Collection created.");
    },
  });
  const update = useMutation({
    mutationFn: () => api.updateCollection(selectedId!, { name: name.trim(), description: description.trim() || null, provider_ids: [...memberIds] }),
    onSuccess: () => {
      invalidate();
      setNotice("Collection saved.");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      setSelectedId(null);
      setCreating(false);
      invalidate();
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

  const visibleProviders = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return providers.filter((provider) =>
      !needle || provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle)),
    );
  }, [providers, query]);

  function beginNew() {
    setCreating(true);
    setSelectedId(null);
    setName("");
    setDescription("");
    setMemberIds(new Set());
    setNotice("");
  }

  function toggleMember(id: string) {
    setMemberIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const isSystem = selected?.kind === "system";
  const pending = create.isPending || update.isPending || sync.isPending;

  return (
    <Modal title="Company collections" onClose={onClose} wide>
      <div className="grid min-h-[31rem] grid-cols-[13rem_minmax(0,1fr)] gap-5">
        <aside className="border-r border-slate-200 pr-4 dark:border-slate-800">
          <button className="btn-secondary w-full justify-center" onClick={beginNew}>New collection</button>
          <div className="mt-4 space-y-1">
            {isLoading && <p className="quiet-state py-4">Loading collections…</p>}
            {collections.map((collection) => (
              <button
                key={collection.id}
                className={`w-full rounded px-3 py-2.5 text-left ${selectedId === collection.id ? "bg-teal-50 text-teal-950 dark:bg-teal-950/40 dark:text-teal-100" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}
                onClick={() => {
                  setCreating(false);
                  setSelectedId(collection.id);
                }}
              >
                <span className="block text-sm font-semibold">{collection.name}</span>
                <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{collection.provider_count} {collection.provider_count === 1 ? "company" : "companies"}{collection.kind === "system" ? " · System" : ""}</span>
              </button>
            ))}
          </div>
          <button className="mt-4 w-full text-left text-xs font-semibold text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-400" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? "Refreshing index…" : "Refresh S&P 500 membership"}
          </button>
        </aside>

        <section className="min-w-0">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <label className="form-label" htmlFor="collection-name">Collection name</label>
              <input id="collection-name" className="form-input" value={name} disabled={isSystem} onChange={(event) => setName(event.target.value)} placeholder="e.g. Payment platforms" />
            </div>
            {selected?.kind === "system" && (
              <span className="mt-6 rounded border border-slate-300 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">System collection</span>
            )}
          </div>
          <div className="mt-3">
            <label className="form-label" htmlFor="collection-description">Research note</label>
            <input id="collection-description" className="form-input" value={description} disabled={isSystem} onChange={(event) => setDescription(event.target.value)} placeholder="Why these companies belong together" />
          </div>

          {isSystem && selected ? (
            <div className="mt-5 rounded-md border border-slate-300 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-900/50">
              <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{selected.description}</p>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div><dt className="text-slate-400">Snapshot</dt><dd className="data-value mt-1 font-semibold">{selected.snapshot_date ?? "Not synchronized"}</dd></div>
                <div><dt className="text-slate-400">Companies</dt><dd className="data-value mt-1 font-semibold">{selected.provider_count}</dd></div>
              </dl>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-200 pt-4 dark:border-slate-700">
                <button className="btn-secondary" onClick={() => start(() => api.verifyCollectionSources(selected.id))}>Verify policy sources</button>
                <button
                  className="btn-primary"
                  onClick={() => {
                    if (confirm(`Analyze every company in ${selected.name} that has a configured source? This can be a long-running job.`)) {
                      start(() => api.analyzeCollection(selected.id));
                      onClose();
                    }
                  }}
                >
                  Analyze collection
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="mt-5 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Companies</h3>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{memberIds.size} selected</p>
                </div>
                <input type="search" className="form-input w-56" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter companies or tickers…" />
              </div>
              <div className="mt-3 max-h-60 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-300 dark:divide-slate-800 dark:border-slate-700">
                {visibleProviders.map((provider) => (
                  <label key={provider.id} className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-900">
                    <input type="checkbox" checked={memberIds.has(provider.id)} onChange={() => toggleMember(provider.id)} className="accent-teal-700" />
                    <CompanyLogo name={provider.name} domain={provider.domain} className="h-7 w-7" />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{provider.name}</span>
                    <span className="data-value text-xs text-slate-400">{provider.tickers.join(", ")}</span>
                  </label>
                ))}
              </div>
            </>
          )}

          {notice && <p className="mt-3 text-xs font-medium text-teal-700 dark:text-teal-400">{notice}</p>}
          {(create.isError || update.isError || sync.isError) && <p className="mt-3 text-xs text-red-600">{((create.error || update.error || sync.error) as Error).message}</p>}

          {!isSystem && (
            <div className="mt-4 flex items-center justify-between border-t border-slate-200 pt-4 dark:border-slate-800">
              {selected ? <button className="text-xs font-semibold text-red-600 hover:underline" onClick={() => confirm(`Delete ${selected.name}?`) && remove.mutate(selected.id)}>Delete collection</button> : <span />}
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={onClose}>Cancel</button>
                <button className="btn-primary" disabled={pending || !name.trim()} onClick={() => selected ? update.mutate() : create.mutate()}>{pending ? "Saving…" : selected ? "Save collection" : "Create collection"}</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </Modal>
  );
}
