import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { api } from "../../api/client";
import type { BulkActionPreview, BulkOperation, RetentionPreview } from "../../api/types";
import { useCollections, useProviders } from "../../hooks/queries";
import { materialValue, MdCheckbox, MdFilledButton, MdOutlinedButton, MdOutlinedTextField, MdRadio } from "../MaterialControls";
import { Modal } from "../Modal";

type Mode = "pipeline" | "retention";

export function BulkActionsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: collections = [], isLoading: loadingCollections } = useCollections();
  const [mode, setMode] = useState<Mode>("pipeline");
  const [operation, setOperation] = useState<BulkOperation>("generate");
  const [providerIds, setProviderIds] = useState<Set<string>>(new Set());
  const [collectionIds, setCollectionIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<BulkActionPreview | null>(null);
  const [retentionDays, setRetentionDays] = useState("90");
  const [retentionPreview, setRetentionPreview] = useState<RetentionPreview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"preview" | "run" | "retention-preview" | "retention-run" | null>(null);

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

  function parseRetentionDays() {
    const days = Number(retentionDays);
    if (!Number.isInteger(days) || days < 1 || days > 36500) {
      setError("Enter a whole number of days from 1 to 36,500.");
      return null;
    }
    return days;
  }

  async function previewRetention() {
    const days = parseRetentionDays();
    if (!days) return;
    setError("");
    setPending("retention-preview");
    try {
      setRetentionPreview(await api.previewRetention(days));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview cleanup.");
    } finally {
      setPending(null);
    }
  }

  async function queueRetentionCleanup() {
    const days = parseRetentionDays();
    if (!days) return;
    setError("");
    setPending("retention-run");
    try {
      await api.cleanupRetention(days);
      invalidate();
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not queue cleanup.");
    } finally {
      setPending(null);
    }
  }

  return (
    <Modal title="Bulk tasks and retention" onClose={onClose} wide>
      <div className="m3-bulk-tabs" role="tablist" aria-label="Bulk task options">
        <button className={`m3-bulk-tab ${mode === "pipeline" ? "m3-bulk-tab-selected" : ""}`} role="tab" aria-selected={mode === "pipeline"} onClick={() => { setMode("pipeline"); setError(""); }}>
          Pipeline tasks
        </button>
        <button className={`m3-bulk-tab ${mode === "retention" ? "m3-bulk-tab-selected" : ""}`} role="tab" aria-selected={mode === "retention"} onClick={() => { setMode("retention"); setError(""); }}>
          Retention cleanup
        </button>
      </div>

      {mode === "pipeline" ? (
        <section className="pt-4" role="tabpanel">
          <fieldset>
            <legend className="form-label">Task to queue</legend>
            <div className="flex flex-col gap-2 sm:flex-row">
              {(["generate", "score"] as BulkOperation[]).map((kind) => (
                <label key={kind} className={`m3-bulk-operation ${operation === kind ? "m3-bulk-operation-selected" : ""}`}>
                  <MdRadio name="bulk-operation" value={kind} checked={operation === kind} onChange={() => { setOperation(kind); resetPipelinePreview(); }} />
                  <span><span className="block font-semibold">{kind === "generate" ? "Generate policy graph analyses" : "Score completed analyses"}</span><span className="m3-bulk-operation-description mt-0.5 block text-xs leading-5">{kind === "generate" ? "Process the most recent policy for each selected company." : "Create missing privacy and GDPR assessments for completed policies."}</span></span>
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
              <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">Individual companies</h3><span className="m3-bulk-selection-count">{providerIds.size} selected</span></div>
              <MdOutlinedTextField type="search" className="mt-2 w-full" value={query} onInput={(event) => setQuery(materialValue(event))} label="Filter companies or tickers" />
              <div className="m3-bulk-selection-list mt-2 max-h-40">
                {loadingProviders && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">Loading companies…</p>}
                {!loadingProviders && filteredProviders.length === 0 && <p className="p-3 text-sm text-[var(--md-sys-color-on-surface-variant)]">No companies match this filter.</p>}
                {filteredProviders.map((provider) => <label key={provider.id} className="m3-bulk-selection-row"><MdCheckbox checked={providerIds.has(provider.id)} onChange={() => toggle(setProviderIds, provider.id)} /><span className="min-w-0 flex-1 truncate text-sm">{provider.name}</span><span className="data-value text-xs text-[var(--md-sys-color-on-surface-variant)]">{provider.tickers.join(", ")}</span></label>)}
              </div>
            </section>
          </div>

          {preview && <div className="m3-bulk-preview mt-5"><p className="font-semibold">Ready to queue {preview.eligible_count} {preview.eligible_count === 1 ? "policy" : "policies"} across {preview.provider_count} {preview.provider_count === 1 ? "company" : "companies"}.</p><p className="mt-1">{preview.skipped_count ? `${preview.skipped_count} selected companies have no eligible policy and will be skipped.` : "Every selected company has eligible work."}</p></div>}
          {error && <p role="alert" className="mt-4 status-error">{error}</p>}
          <div className="workspace-rule mt-5 flex justify-end gap-2 border-t pt-4"><MdOutlinedButton onClick={onClose}>Cancel</MdOutlinedButton>{preview ? <MdFilledButton disabled={pending !== null || preview.eligible_count === 0} onClick={queuePipeline}>{pending === "run" ? "Queueing…" : "Confirm and queue"}</MdFilledButton> : <MdFilledButton disabled={pending !== null} onClick={previewPipeline}>{pending === "preview" ? "Previewing…" : "Preview batch"}</MdFilledButton>}</div>
        </section>
      ) : (
        <section className="pt-4" role="tabpanel">
          <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">Remove policy history and its stored source and artifact files older than a chosen retention period. This action cannot be undone after the queued task completes.</p>
          <div className="mt-5 flex max-w-xs items-center gap-2"><MdOutlinedTextField id="retention-days" className="w-full" label="Keep history from the last" type="number" min="1" max="36500" step="1" value={retentionDays} suffixText="days" onInput={(event) => { setRetentionDays(materialValue(event)); setRetentionPreview(null); }} /></div>
          {retentionPreview && <div className="m3-bulk-retention-preview mt-5"><p className="font-semibold">Cleanup will remove {retentionPreview.policy_count} {retentionPreview.policy_count === 1 ? "policy record" : "policy records"}, {retentionPreview.analysis_result_count} assessment results, and up to {retentionPreview.artifact_count} stored files.</p><p className="mt-1">The matching history belongs to {retentionPreview.provider_count} {retentionPreview.provider_count === 1 ? "company" : "companies"} and predates {new Date(retentionPreview.cutoff).toLocaleString()}.</p></div>}
          {error && <p role="alert" className="mt-4 status-error">{error}</p>}
          <div className="workspace-rule mt-5 flex justify-end gap-2 border-t pt-4"><MdOutlinedButton onClick={onClose}>Cancel</MdOutlinedButton>{retentionPreview ? <MdFilledButton className="material-error" disabled={pending !== null || retentionPreview.policy_count === 0} onClick={queueRetentionCleanup}>{pending === "retention-run" ? "Queueing…" : "Confirm cleanup"}</MdFilledButton> : <MdFilledButton disabled={pending !== null} onClick={previewRetention}>{pending === "retention-preview" ? "Previewing…" : "Preview cleanup"}</MdFilledButton>}</div>
        </section>
      )}
    </Modal>
  );
}
