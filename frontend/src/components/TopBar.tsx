import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { useTaskRunner } from "../hooks/useTaskRunner";
import { AddProviderModal } from "./modals/AddProviderModal";
import { ImportCsvModal } from "./modals/ImportCsvModal";

export function TopBar() {
  const qc = useQueryClient();
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["policies"] });
  };
  const { start, task, isRunning } = useTaskRunner(invalidateAll);

  return (
    <>
      <header className="flex flex-shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-3 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-brand">Poligrapher</span>
          <span className="text-xs text-zinc-400 dark:text-zinc-500">privacy policy analyzer</span>
        </div>
        <div className="flex items-center gap-2">
          {task?.label && (
            <span className="mr-2 text-xs text-zinc-500 dark:text-zinc-400">
              {task.label}: {task.completed}/{task.total}
              {task.failed > 0 ? ` (${task.failed} failed)` : ""}
              {task.status === "done" ? " ✓" : task.status === "failed" ? " ✕" : "…"}
            </span>
          )}
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

      {showAddProvider && <AddProviderModal onClose={() => setShowAddProvider(false)} />}
      {showImport && <ImportCsvModal onClose={() => setShowImport(false)} />}
    </>
  );
}
