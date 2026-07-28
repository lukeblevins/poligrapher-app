import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { api } from "../../api/client";
import type { BulkActionPreview, BulkOperation } from "../../api/types";
import { useCollections, useProviders } from "../../hooks/queries";
import { materialValue, MdCheckbox, MdFilledButton, MdOutlinedButton, MdOutlinedTextField, MdRadio } from "../MaterialControls";
import { Modal } from "../Modal";

export function BulkActionsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: collections = [], isLoading: loadingCollections } = useCollections();
  const [operation, setOperation] = useState<BulkOperation>("generate");
  const [providerIds, setProviderIds] = useState<Set<string>>(new Set());
  const [collectionIds, setCollectionIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<BulkActionPreview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"preview" | "run" | null>(null);

  const filteredProviders = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return providers.filter((provider) => !needle || provider.name.toLowerCase().includes(needle) || provider.tickers.some((ticker) => ticker.toLowerCase().includes(needle)));
  }, [providers, query]);

  const selectionBody = () => ({ operation, provider_ids: [...providerIds], collection_ids: [...collectionIds] });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["tasks"] });
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["policies"] });
  };
  const resetPipelinePreview = () => {
    setPreview(null);
    setError("");
  };
  const toggle = (set: Dispatch<SetStateAction<Set<string>>>, id: string) => {
    set((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    resetPipelinePreview();
  };

  async function previewPipeline() {
    if (!providerIds.size && !collectionIds.size) {
      setError("Choose at least one company or collection before previewing the work.");
      return;
    }
    setError("");
    setPending("preview");
    try {
      setPreview(await api.previewBulkAction(selectionBody()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview this batch.");
    } finally {
      setPending(null);
    }
  }

  async function queuePipeline() {
    setError("");
    setPending("run");
    try {
      await api.runBulkAction(selectionBody());
      invalidate();
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not queue this batch.");
    } finally {
      setPending(null);
    }
  }

  return (
    <Modal title="New task" onClose={onClose} wide showCloseButton={false} className="m3-bulk-dialog">
        <section>
          <fieldset>
            <legend className="form-label">Task</legend>
            <div className="flex flex-col gap-2 sm:flex-row">
              {(["generate", "score"] as BulkOperation[]).map((kind) => (
                <label key={kind} className={`m3-bulk-operation ${operation === kind ? "m3-bulk-operation-selected" : ""}`}>
                  <MdRadio name="bulk-operation" value={kind} checked={operation === kind} onChange={() => { setOperation(kind); resetPipelinePreview(); }} />
                  <span><span className="block font-semibold">{kind === "generate" ? "Analyze policies" : "Score analyses"}</span><span className="m3-bulk-operation-description mt-0.5 block text-xs leading-5">{kind === "generate" ? "Create graph output for companies that are not analyzed yet." : "Add missing privacy and GDPR scores."}</span></span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-5 grid gap-5 md:grid-cols-2">
            <section>
              <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">Collections</h3><span className="m3-bulk-selection-count">{collectionIds.size} selected</span></div>
              <div className="m3-bulk-selection-list mt-2 max-h-40">
                {loadingCollections && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">Loading collections…</p>}
                {!loadingCollections && collections.length === 0 && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">No collections yet.</p>}
                {collections.map((collection) => <label key={collection.id} className="m3-bulk-selection-row"><MdCheckbox checked={collectionIds.has(collection.id)} onChange={() => toggle(setCollectionIds, collection.id)} /><span className="min-w-0 flex-1 truncate text-sm">{collection.name}</span><span className="data-value text-xs text-[var(--md-sys-color-on-surface-variant)]">{collection.provider_count}</span></label>)}
              </div>
            </section>
            <section>
              <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">Companies</h3><span className="m3-bulk-selection-count">{providerIds.size} selected</span></div>
              <MdOutlinedTextField type="search" className="mt-2 w-full" value={query} onInput={(event) => setQuery(materialValue(event))} label="Search companies" />
              <div className="m3-bulk-selection-list mt-2 max-h-40">
                {loadingProviders && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">Loading companies…</p>}
                {!loadingProviders && filteredProviders.length === 0 && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">No companies match this filter.</p>}
                {filteredProviders.map((provider) => <label key={provider.id} className="m3-bulk-selection-row"><MdCheckbox checked={providerIds.has(provider.id)} onChange={() => toggle(setProviderIds, provider.id)} /><span className="min-w-0 flex-1 truncate text-sm">{provider.name}</span><span className="data-value text-xs text-[var(--md-sys-color-on-surface-variant)]">{provider.tickers.join(", ")}</span></label>)}
              </div>
            </section>
          </div>

          {preview && <div className="m3-bulk-preview mt-5"><p className="font-semibold">{operation === "generate" ? `Ready to analyze ${preview.eligible_count} ${preview.eligible_count === 1 ? "company" : "companies"}.` : `Ready to score ${preview.eligible_count} ${preview.eligible_count === 1 ? "policy" : "policies"}.`}</p><p className="mt-1">{preview.skipped_count ? `${preview.skipped_count} selected companies are already complete or do not have a policy source.` : "Every selected company has eligible work."}</p></div>}
          {error && <p role="alert" className="mt-4 status-error">{error}</p>}
          <div className="m3-dialog-actions mt-5 flex justify-end gap-2"><MdOutlinedButton onClick={onClose}>Cancel</MdOutlinedButton>{preview ? <MdFilledButton disabled={pending !== null || preview.eligible_count === 0} onClick={queuePipeline}>{pending === "run" ? "Queueing…" : "Queue task"}</MdFilledButton> : <MdFilledButton disabled={pending !== null} onClick={previewPipeline}>{pending === "preview" ? "Previewing…" : "Preview"}</MdFilledButton>}</div>
        </section>
    </Modal>
  );
}
