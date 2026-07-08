import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Provider } from "../api/types";
import { useTaskRunner } from "../hooks/useTaskRunner";
import { StatusCenter } from "./StatusCenter";
import { AddProviderModal } from "./modals/AddProviderModal";
import { ImportCsvModal } from "./modals/ImportCsvModal";

export function TopBar({ onProviderCreated }: { onProviderCreated?: (p: Provider) => void }) {
  const qc = useQueryClient();
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["policies"] });
  };
  const { start, isRunning } = useTaskRunner(invalidateAll);

  return (
    <>
      <header className="flex flex-shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-3 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-brand">Privacy Policy Analyzer</span>
          <span className="text-xs text-zinc-400 dark:text-zinc-500">
            Compliance &amp; readability scoring
          </span>
        </div>
        <div className="flex items-center gap-2">
          <StatusCenter />
          <button className="btn-secondary" onClick={() => setShowAddProvider(true)}>
            + Provider
          </button>
          <button className="btn-secondary" onClick={() => setShowImport(true)}>
            Import CSV
          </button>
          <button
            className="btn-secondary"
            disabled={isRunning}
            onClick={() => start(api.refreshAll)}
          >
            Refresh Pending
          </button>
          <button
            className="btn-primary"
            disabled={isRunning}
            onClick={() => start(api.scoreAll)}
          >
            Score All
          </button>
        </div>
      </header>

      {showAddProvider && (
        <AddProviderModal
          onClose={() => setShowAddProvider(false)}
          onCreated={onProviderCreated}
        />
      )}
      {showImport && <ImportCsvModal onClose={() => setShowImport(false)} />}
    </>
  );
}
