import { useState } from "react";

import type { CapturedPolicyText } from "../../api/types";
import { materialValue, MdFilledButton, MdOutlinedButton, MdOutlinedTextField } from "../MaterialControls";
import { Modal } from "../Modal";

interface Props {
  companyName: string;
  sourceUrl: string;
  pending: boolean;
  error: unknown;
  onClose: () => void;
  onSubmit: (capture: CapturedPolicyText) => void;
}

function validWebUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function CapturedPolicyModal({ companyName, sourceUrl, pending, error, onClose, onSubmit }: Props) {
  const [title, setTitle] = useState(`${companyName} Privacy Policy`);
  const [url, setUrl] = useState(sourceUrl);
  const [captureDate, setCaptureDate] = useState(new Date().toISOString().slice(0, 10));
  const [text, setText] = useState("");
  const normalizedUrl = url.trim();
  const normalizedText = text.trim();
  const ready = title.trim().length > 0
    && validWebUrl(normalizedUrl)
    && /^\d{4}-\d{2}-\d{2}$/.test(captureDate)
    && normalizedText.length >= 500;

  return (
    <Modal title="Analyze captured policy text" onClose={onClose} wide>
      <p className="text-sm leading-6 text-[var(--md-sys-color-on-surface-variant)]">
        Use this when an official policy is visible in a browser but automated retrieval fails. The source URL and capture date are embedded in the stored document.
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <MdOutlinedTextField className="w-full" label="Document title" value={title} onInput={(event) => setTitle(materialValue(event))} />
        <MdOutlinedTextField className="w-full" type="date" label="Capture date" value={captureDate} onInput={(event) => setCaptureDate(materialValue(event))} />
      </div>
      <MdOutlinedTextField
        className="mt-4 w-full"
        type="url"
        label="Official source URL"
        value={url}
        onInput={(event) => setUrl(materialValue(event))}
        error={Boolean(normalizedUrl && !validWebUrl(normalizedUrl))}
        errorText="Enter a complete address beginning with http:// or https://."
      />
      <MdOutlinedTextField
        className="mt-4 w-full"
        type="textarea"
        rows={12}
        label="Policy text"
        value={text}
        onInput={(event) => setText(materialValue(event))}
        supportingText={`${normalizedText.length.toLocaleString()} characters; at least 500 required`}
      />
      {Boolean(error) && (
        <p role="alert" className="mt-4 status-error">
          {error instanceof Error ? error.message : "The captured policy could not be queued."}
        </p>
      )}
      <div className="m3-dialog-actions mt-5 flex justify-end gap-2">
        <MdOutlinedButton disabled={pending} onClick={onClose}>Cancel</MdOutlinedButton>
        <MdFilledButton
          disabled={pending || !ready}
          onClick={() => onSubmit({
            title: title.trim(),
            source_url: normalizedUrl,
            capture_date: captureDate,
            text: normalizedText,
          })}
        >
          {pending ? "Queueing…" : "Analyze text"}
        </MdFilledButton>
      </div>
    </Modal>
  );
}
