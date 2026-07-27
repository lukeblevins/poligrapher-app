import { useState } from "react";

import type { ImportSummary } from "../../api/types";
import { useImportCsv } from "../../hooks/queries";
import { MdFilledButton, MdOutlinedButton } from "../MaterialControls";
import { Modal } from "../Modal";

export function ImportCsvModal({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const importCsv = useImportCsv();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    try {
      setSummary(await importCsv.mutateAsync(file));
    } catch {
      /* error surfaced below */
    }
  }

  return (
    <Modal title="Import companies from CSV" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs leading-5 text-[var(--md-sys-color-on-surface-variant)]">
          CSV columns: Provider, Policy URL, Industry, Source, Date, Status, Score, GDPR Score,
          Graph Kind, Pipeline Status, Pipeline Errors.
        </p>
        <label className="form-label" htmlFor="company-csv-file">CSV file</label>
        <input
          id="company-csv-file"
          className="m3-file-input"
          type="file"
          accept=".csv"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setSummary(null);
          }}
          required
        />
        {summary && (
          <p role="status" className="status-success">
            {summary.created} created, {summary.skipped} skipped, {summary.errors} errors.
          </p>
        )}
        {importCsv.isError && (
          <p role="alert" className="status-error">
            {(importCsv.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <MdOutlinedButton type="button" onClick={onClose}>
            {summary ? "Done" : "Cancel"}
          </MdOutlinedButton>
          <MdFilledButton type="submit" disabled={importCsv.isPending || !file || Boolean(summary)}>
            {importCsv.isPending ? "Importing…" : summary ? "Imported" : "Import companies"}
          </MdFilledButton>
        </div>
      </form>
    </Modal>
  );
}
