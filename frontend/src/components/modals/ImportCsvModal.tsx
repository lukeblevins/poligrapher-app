import { useState } from "react";

import type { ImportSummary } from "../../api/types";
import { useImportCsv } from "../../hooks/queries";
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
    <Modal title="Import policies from CSV" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          CSV columns: Provider, Policy URL, Industry, Source, Date, Status, Score, GDPR Score,
          Graph Kind, Pipeline Status, Pipeline Errors.
        </p>
        <input
          className="form-input"
          type="file"
          accept=".csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        {summary && (
          <p className="rounded bg-green-50 px-3 py-2 text-xs text-green-700 dark:bg-green-950 dark:text-green-400">
            {summary.created} created, {summary.skipped} skipped, {summary.errors} errors.
          </p>
        )}
        {importCsv.isError && (
          <p className="text-xs text-red-600 dark:text-red-400">
            {(importCsv.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            {summary ? "Done" : "Cancel"}
          </button>
          <button type="submit" className="btn-primary" disabled={importCsv.isPending || !file}>
            {importCsv.isPending ? "Importing…" : "Import"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
