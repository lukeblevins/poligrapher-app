import { useState } from "react";

import { useAddPolicy } from "../../hooks/queries";
import { Modal } from "../Modal";

export function AddPolicyModal({
  providerId,
  onClose,
}: {
  providerId: string;
  onClose: () => void;
}) {
  const [source, setSource] = useState<"webpage" | "pdf">("webpage");
  const [url, setUrl] = useState("");
  const [captureDate, setCaptureDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const addPolicy = useAddPolicy(providerId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const form = new FormData();
    form.append("source", source);
    form.append("capture_date", captureDate);
    if (source === "webpage") {
      form.append("url", url.trim());
    } else if (file) {
      form.append("pdf_file", file);
    }
    try {
      await addPolicy.mutateAsync(form);
      onClose();
    } catch {
      /* error surfaced below */
    }
  }

  return (
    <Modal title="Add policy" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="form-label">Source</label>
          <select
            className="form-input"
            value={source}
            onChange={(e) => setSource(e.target.value as "webpage" | "pdf")}
          >
            <option value="webpage">Webpage (URL)</option>
            <option value="pdf">PDF upload</option>
          </select>
        </div>

        {source === "webpage" ? (
          <div>
            <label className="form-label">Policy URL</label>
            <input
              className="form-input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/privacy"
              required
              autoFocus
            />
          </div>
        ) : (
          <div>
            <label className="form-label">PDF file</label>
            <input
              className="form-input"
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
        )}

        <div>
          <label className="form-label">Capture date (optional)</label>
          <input
            className="form-input"
            type="date"
            value={captureDate}
            onChange={(e) => setCaptureDate(e.target.value)}
          />
        </div>

        {addPolicy.isError && (
          <p className="text-xs text-red-600 dark:text-red-400">
            {(addPolicy.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={addPolicy.isPending}>
            {addPolicy.isPending ? "Adding…" : "Add"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
