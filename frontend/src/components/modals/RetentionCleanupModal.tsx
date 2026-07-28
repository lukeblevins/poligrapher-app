import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { RetentionPreview } from "../../api/types";
import { materialValue, MdFilledButton, MdOutlinedButton, MdOutlinedTextField } from "../MaterialControls";
import { Modal } from "../Modal";

export function RetentionCleanupModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [days, setDays] = useState("90");
  const [preview, setPreview] = useState<RetentionPreview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"preview" | "delete" | null>(null);

  function parsedDays() {
    const value = Number(days);
    if (!Number.isInteger(value) || value < 1 || value > 36500) {
      setError("Enter a whole number from 1 to 36,500.");
      return null;
    }
    return value;
  }

  async function previewCleanup() {
    const value = parsedDays();
    if (!value) return;
    setError("");
    setPending("preview");
    try {
      setPreview(await api.previewRetention(value));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview cleanup.");
    } finally {
      setPending(null);
    }
  }

  async function deleteHistory() {
    const value = parsedDays();
    if (!value) return;
    setError("");
    setPending("delete");
    try {
      await api.cleanupRetention(value);
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["policies"] });
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not queue cleanup.");
    } finally {
      setPending(null);
    }
  }

  return (
    <Modal title="Delete old history" onClose={onClose} showCloseButton={false} className="m3-bulk-dialog">
      <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
        Delete policy history and stored files older than the selected period. This cannot be undone.
      </p>
      <MdOutlinedTextField
        id="retention-days"
        className="mt-5 w-full"
        label="Keep recent history"
        type="number"
        min="1"
        max="36500"
        step="1"
        value={days}
        suffixText="days"
        onInput={(event) => {
          setDays(materialValue(event));
          setPreview(null);
        }}
      />
      {preview && (
        <div className="m3-bulk-retention-preview mt-5">
          <p className="font-semibold">
            Delete {preview.policy_count} {preview.policy_count === 1 ? "policy record" : "policy records"}, {preview.analysis_result_count} assessment results, and up to {preview.artifact_count} stored files.
          </p>
          <p className="mt-1">
            This history covers {preview.provider_count} {preview.provider_count === 1 ? "company" : "companies"} and predates {new Date(preview.cutoff).toLocaleString()}.
          </p>
        </div>
      )}
      {error && <p role="alert" className="mt-4 status-error">{error}</p>}
      <div className="m3-dialog-actions mt-5 flex justify-end gap-2">
        <MdOutlinedButton onClick={onClose}>Cancel</MdOutlinedButton>
        {preview ? (
          <MdFilledButton className="material-error" disabled={pending !== null || preview.policy_count === 0} onClick={deleteHistory}>
            {pending === "delete" ? "Queueing…" : "Delete history"}
          </MdFilledButton>
        ) : (
          <MdFilledButton disabled={pending !== null} onClick={previewCleanup}>
            {pending === "preview" ? "Previewing…" : "Preview"}
          </MdFilledButton>
        )}
      </div>
    </Modal>
  );
}
