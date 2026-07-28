import checkIcon from "@material-symbols/svg-400/rounded/check_circle.svg?url";
import csvIcon from "@material-symbols/svg-400/rounded/csv.svg?url";
import uploadIcon from "@material-symbols/svg-400/rounded/upload_file.svg?url";
import { useRef, useState, type CSSProperties } from "react";

import type { ImportSummary } from "../../api/types";
import { useImportCsv } from "../../hooks/queries";
import { MdFilledButton, MdTextButton } from "../MaterialControls";
import { Modal } from "../Modal";

function MaterialIcon({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

export function ImportCsvModal({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const importCsv = useImportCsv();

  function chooseFile(nextFile: File | null) {
    setFile(nextFile);
    setSummary(null);
    importCsv.reset();
  }

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
    <Modal title="Import companies" onClose={onClose} className="import-csv-dialog" showCloseButton={false}>
      <form onSubmit={submit} className="import-csv-flow">
        <p className="import-csv-intro">Upload a CSV with one row for each privacy policy.</p>
        <input
          ref={inputRef}
          id="company-csv-file"
          className="sr-only"
          type="file"
          accept=".csv"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          className={`import-csv-picker ${dragActive ? "import-csv-picker-active" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            const dropped = event.dataTransfer.files[0] ?? null;
            if (dropped?.name.toLowerCase().endsWith(".csv")) chooseFile(dropped);
          }}
        >
          <span className="import-csv-picker-icon"><MaterialIcon src={file ? csvIcon : uploadIcon} /></span>
          <span className="import-csv-picker-copy">
            <strong>{file ? file.name : "Choose a CSV file"}</strong>
            <span>{file ? `${Math.max(1, Math.round(file.size / 1024))} KB. Choose another file` : "or drag and drop it here"}</span>
          </span>
        </button>

        <details className="import-csv-format">
          <summary>
            <span>CSV format</span>
            <span>2 required columns</span>
          </summary>
          <div>
            <p><strong>Required:</strong> Provider, Policy URL</p>
            <p><strong>Optional:</strong> Industry, Source, Date, Status, Score, GDPR Score, Graph Kind, Pipeline Status, Pipeline Errors</p>
          </div>
        </details>

        {summary && (
          <div role="status" className="import-csv-summary">
            <span className="import-csv-summary-icon"><MaterialIcon src={checkIcon} /></span>
            <div>
              <strong>Import complete</strong>
              <p>{summary.created} added, {summary.skipped} already existed, {summary.errors} failed</p>
            </div>
          </div>
        )}
        {importCsv.isError && (
          <p role="alert" className="status-error">
            {(importCsv.error as Error).message}
          </p>
        )}
        <div className="import-csv-actions">
          <MdTextButton type="button" onClick={onClose}>
            {summary ? "Done" : "Cancel"}
          </MdTextButton>
          {!summary && (
            <MdFilledButton type="submit" disabled={importCsv.isPending || !file}>
              {importCsv.isPending ? "Importing…" : "Import"}
            </MdFilledButton>
          )}
        </div>
      </form>
    </Modal>
  );
}
