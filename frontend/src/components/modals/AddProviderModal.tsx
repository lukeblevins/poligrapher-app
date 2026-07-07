import { useState } from "react";

import { useCreateProvider } from "../../hooks/queries";
import { Modal } from "../Modal";

export function AddProviderModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const createProvider = useCreateProvider();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createProvider.mutateAsync({ name: name.trim(), industry: industry.trim() || null });
      onClose();
    } catch {
      /* error surfaced below */
    }
  }

  return (
    <Modal title="Add provider" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="form-label">Name</label>
          <input
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
          />
        </div>
        <div>
          <label className="form-label">Industry (optional)</label>
          <input
            className="form-input"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
          />
        </div>
        {createProvider.isError && (
          <p className="text-xs text-red-600 dark:text-red-400">
            {(createProvider.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={createProvider.isPending}>
            {createProvider.isPending ? "Adding…" : "Add"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
