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

export function TopBar({
  onProviderCreated,
  onViewRun,
}: {
  onProviderCreated?: (p: Provider) => void;
  onViewRun?: (task: TaskStatus) => void;
}) {
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
      <header className="relative z-40 flex min-h-16 flex-shrink-0 items-center justify-between gap-2 border-b border-slate-300 bg-white px-3 py-2 sm:px-5 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <svg viewBox="0 0 32 32" fill="none" className="h-7 w-7 flex-none text-teal-700 sm:h-8 sm:w-8 dark:text-teal-400" aria-hidden="true">
            <circle cx="7" cy="16" r="3" fill="currentColor" />
            <circle cx="24" cy="8" r="3" fill="currentColor" />
            <circle cx="24" cy="24" r="3" fill="currentColor" />
            <path d="m10 15 11-5M10 17l11 5" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          <div className="min-w-0">
            <div className="truncate font-display text-sm font-bold tracking-tight text-slate-950 sm:text-base dark:text-white">
              <span className="sm:hidden">Policy Analyzer</span>
              <span className="hidden sm:inline">Privacy Policy Analyzer</span>
            </div>
            <div className="hidden items-center gap-1.5 text-[11px] font-medium text-slate-500 sm:flex dark:text-slate-400">
              <span>Privacy policy research</span>
              <span aria-hidden="true">·</span>
              <button className="transition-colors hover:text-teal-700 hover:underline dark:hover:text-teal-400" onClick={() => setShowAttribution(true)}>
                Sources &amp; attribution
              </button>
            </div>
          </div>
        </div>
        <div className="flex flex-none items-center gap-1 sm:gap-2">
          <StatusCenter onViewRun={onViewRun} />
          <span className="mx-0.5 hidden h-6 w-px bg-slate-200 sm:block dark:bg-slate-800" aria-hidden="true" />
          <button className="btn-primary px-2.5 sm:px-3.5" onClick={() => setShowAddProvider(true)} aria-label="Add company">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4 sm:mr-1.5" aria-hidden="true">
              <path d="M10 4v12M4 10h12" strokeLinecap="round" />
            </svg>
            <span className="hidden sm:inline">Add company</span>
          </button>
          <div ref={actionsDisclosureRef} className="relative">
            <button
              ref={actionsTriggerRef}
              className="btn-secondary px-2.5 sm:px-3.5"
              aria-label="Workspace actions"
              aria-haspopup="true"
              aria-expanded={showActions}
              aria-controls="workspace-actions-panel"
              onClick={() => setShowActions((open) => !open)}
            >
              <span className="hidden lg:inline">Workspace actions</span>
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 lg:hidden" aria-hidden="true">
                <circle cx="4" cy="10" r="1.5" /><circle cx="10" cy="10" r="1.5" /><circle cx="16" cy="10" r="1.5" />
              </svg>
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className={`ml-2 hidden h-4 w-4 transition-transform lg:block ${showActions ? "rotate-180" : ""}`} aria-hidden="true">
                <path d="m6 8 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {showActions && (
              <div
                id="workspace-actions-panel"
                role="group"
                aria-labelledby="workspace-actions-title"
                className="isolate fixed inset-x-3 top-[4.25rem] z-50 max-h-[calc(100dvh-5rem)] w-auto overflow-y-auto rounded-md border border-slate-300 bg-white p-1 shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:z-20 sm:mt-2 sm:max-h-[calc(100dvh-5.5rem)] sm:w-[min(20rem,calc(100vw-1.5rem))] dark:border-slate-700 dark:bg-slate-950"
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
                  <button
                    className="w-full rounded-b px-3 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-900"
                    onClick={() => {
                      setShowActions(false);
                      setShowAttribution(true);
                    }}
                  >
                    <span className="block text-sm font-semibold">Sources and attribution</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">Review the research tools and public datasets used by this workspace.</span>
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
