import { useState } from "react";

import { useAddPolicy } from "../../hooks/queries";
import { Modal } from "../Modal";
import { SelectMenu } from "../SelectMenu";

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
          <span className="form-label">Source</span>
          <SelectMenu
            label="Policy source type"
            heading="Source"
            value={source}
            options={[
              { value: "webpage", label: "Webpage (URL)" },
              { value: "pdf", label: "PDF upload" },
            ]}
            onChange={(value) => setSource(value as "webpage" | "pdf")}
          />
        </div>

        {source === "webpage" ? (
          <div>
            <label className="form-label" htmlFor="new-policy-url">Policy URL</label>
            <input
              id="new-policy-url"
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
            <label className="form-label" htmlFor="new-policy-file">PDF file</label>
            <input
              id="new-policy-file"
              className="form-input"
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
        )}

        <div>
          <label className="form-label" htmlFor="new-policy-date">Capture date (optional)</label>
          <input
            id="new-policy-date"
            className="form-input"
            type="date"
            value={captureDate}
            onChange={(e) => setCaptureDate(e.target.value)}
          />
        </div>

        {addPolicy.isError && (
          <p role="alert" className="status-error">
            {(addPolicy.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={addPolicy.isPending}>
            {addPolicy.isPending ? "Adding…" : "Add policy"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
