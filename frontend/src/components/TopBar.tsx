import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Provider, TaskStatus } from "../api/types";
import { useTaskRunner } from "../hooks/useTaskRunner";
import { StatusCenter } from "./StatusCenter";
import { AttributionModal } from "./AttributionModal";
import { AddProviderModal } from "./modals/AddProviderModal";
import { CollectionsModal } from "./modals/CollectionsModal";
import { ImportCsvModal } from "./modals/ImportCsvModal";

export function TopBar({ onProviderCreated }: { onProviderCreated?: (p: Provider) => void }) {
  const qc = useQueryClient();
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showCollections, setShowCollections] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const [showAttribution, setShowAttribution] = useState(false);
  const actionsDisclosureRef = useRef<HTMLDivElement>(null);
  const actionsTriggerRef = useRef<HTMLButtonElement>(null);

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["policies"] });
  };
  const { start, isRunning } = useTaskRunner(invalidateAll);

  useEffect(() => {
    if (!showActions) return;
    const closeOutside = (event: PointerEvent | FocusEvent) => {
      const target = event.target;
      if (target instanceof Node && !actionsDisclosureRef.current?.contains(target)) {
        setShowActions(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowActions(false);
        actionsTriggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside, true);
    document.addEventListener("focusin", closeOutside, true);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside, true);
      document.removeEventListener("focusin", closeOutside, true);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [showActions]);

  function startBatchAction(action: () => Promise<TaskStatus>) {
    setShowActions(false);
    start(action);
  }

  return (
    <>
      <header className="relative z-40 flex min-h-16 flex-shrink-0 items-center justify-between border-b border-slate-300 bg-white px-5 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center gap-3">
          <svg viewBox="0 0 32 32" fill="none" className="h-8 w-8 text-teal-700 dark:text-teal-400" aria-hidden="true">
            <circle cx="7" cy="16" r="3" fill="currentColor" />
            <circle cx="24" cy="8" r="3" fill="currentColor" />
            <circle cx="24" cy="24" r="3" fill="currentColor" />
            <path d="m10 15 11-5M10 17l11 5" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          <div>
            <div className="font-display text-base font-bold tracking-tight text-slate-950 dark:text-white">Privacy Policy Analyzer</div>
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
              <span>Privacy policy research</span>
              <span aria-hidden="true">·</span>
              <button className="transition-colors hover:text-teal-700 hover:underline dark:hover:text-teal-400" onClick={() => setShowAttribution(true)}>
                Sources &amp; attribution
              </button>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusCenter />
          <span className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-800" />
          <button className="btn-primary" onClick={() => setShowAddProvider(true)}>
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="mr-1.5 h-4 w-4" aria-hidden="true">
              <path d="M10 4v12M4 10h12" strokeLinecap="round" />
            </svg>
            Add company
          </button>
          <div ref={actionsDisclosureRef} className="relative">
            <button
              ref={actionsTriggerRef}
              className="btn-secondary"
              aria-expanded={showActions}
              aria-controls="workspace-actions-panel"
              onClick={() => setShowActions((open) => !open)}
            >
              Workspace actions
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className={`ml-2 h-4 w-4 transition-transform ${showActions ? "rotate-180" : ""}`} aria-hidden="true">
                <path d="m6 8 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {showActions && (
              <div
                id="workspace-actions-panel"
                role="group"
                aria-labelledby="workspace-actions-title"
                className="isolate absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-md border border-slate-300 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-950"
              >
                <div className="px-3 pb-2.5 pt-1.5">
                  <div id="workspace-actions-title" className="section-kicker">Workspace actions</div>
                  <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">Manage records and run operations across the full research dataset.</p>
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  <button
                    className="w-full rounded-t px-3 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-900"
                    onClick={() => {
                      setShowActions(false);
                      setShowCollections(true);
                    }}
                  >
                    <span className="block text-sm font-semibold">Company collections</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">Build research cohorts, refresh S&amp;P 500 membership, or run a collection.</span>
                  </button>
                  <button
                    className="w-full px-3 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-900"
                    onClick={() => {
                      setShowActions(false);
                      setShowImport(true);
                    }}
                  >
                    <span className="block text-sm font-semibold">Import companies from CSV</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">Add or update a prepared policy dataset.</span>
                  </button>
                  <button
                    className="w-full px-3 py-3 text-left transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-slate-900"
                    disabled={isRunning}
                    onClick={() => startBatchAction(api.refreshAll)}
                  >
                    <span className="block text-sm font-semibold">Retry pending analyses</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">Resume records that have not completed processing.</span>
                  </button>
                  <button
                    className="w-full rounded-b px-3 py-3 text-left transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-slate-900"
                    disabled={isRunning}
                    onClick={() => startBatchAction(api.scoreAll)}
                  >
                    <span className="block text-sm font-semibold">Score unscored analyses</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">Generate missing privacy and GDPR assessments.</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {showAddProvider && (
        <AddProviderModal
          onClose={() => setShowAddProvider(false)}
          onCreated={onProviderCreated}
        />
      )}
      {showImport && <ImportCsvModal onClose={() => setShowImport(false)} />}
      {showCollections && <CollectionsModal onClose={() => setShowCollections(false)} />}
      {showAttribution && <AttributionModal onClose={() => setShowAttribution(false)} />}
    </>
  );
}
