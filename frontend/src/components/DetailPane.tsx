import { useState } from "react";

import { AssessmentsPanel } from "./AssessmentsPanel";
import { GraphViewer } from "./GraphViewer";
import { StatsPanel } from "./StatsPanel";

type Tab = "graph" | "stats" | "assessments";

interface Props {
  policyId: string;
  onClose: () => void;
}

const TABS: { id: Tab; label: string }[] = [
  { id: "graph", label: "Graph" },
  { id: "stats", label: "Statistics" },
  { id: "assessments", label: "Assessments" },
];

function TabIcon({ tab }: { tab: Tab }) {
  if (tab === "graph") {
    return (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" className="h-3.5 w-3.5" aria-hidden="true">
        <circle cx="3" cy="8" r="1.5" /><circle cx="12.5" cy="3.5" r="1.5" /><circle cx="12.5" cy="12.5" r="1.5" />
        <path d="m4.5 7.3 6.5-3M4.5 8.7l6.5 3" />
      </svg>
    );
  }
  if (tab === "stats") {
    return (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" className="h-3.5 w-3.5" aria-hidden="true">
        <path d="M2.5 13.5h11M4 12V8.5h2V12M7 12V4.5h2V12M10 12V6.5h2V12" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" className="h-3.5 w-3.5" aria-hidden="true">
      <path d="M5.5 3h7M5.5 8h7M5.5 13h7M2.5 3l.7.7 1.3-1.4M2.5 8l.7.7 1.3-1.4M2.5 13l.7.7 1.3-1.4" />
    </svg>
  );
}

export function DetailPane({ policyId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("graph");

  return (
    <div
      className="flex flex-shrink-0 flex-col border-l border-slate-300 bg-white dark:border-slate-800 dark:bg-slate-900"
      style={{ width: "52%" }}
    >
      <div className="flex flex-shrink-0 items-stretch justify-between border-b border-slate-300 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <div role="tablist" aria-label="Analysis views" className="flex">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls="analysis-detail-panel"
              className={`flex items-center gap-2 border-r border-slate-300 px-4 py-3 text-xs font-semibold transition-colors first:border-l dark:border-slate-800 ${
                tab === t.id
                  ? "bg-white text-slate-950 dark:bg-slate-900 dark:text-white"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
              }`}
              onClick={() => setTab(t.id)}
            >
              <TabIcon tab={t.id} />
              {t.label}
            </button>
          ))}
        </div>
        <button
          className="my-auto mr-3 grid h-8 w-8 place-items-center rounded text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          onClick={onClose}
          aria-label="Close panel"
        >
          ✕
        </button>
      </div>

      <div id="analysis-detail-panel" role="tabpanel" className="min-h-0 flex-1 overflow-hidden">
        {tab === "graph" && (
          <div className="h-full">
            <GraphViewer key={policyId} policyId={policyId} />
          </div>
        )}
        {tab === "stats" && (
          <div className="h-full overflow-auto p-4">
            <StatsPanel policyId={policyId} />
          </div>
        )}
        {tab === "assessments" && (
          <div className="h-full overflow-auto p-4">
            <AssessmentsPanel policyId={policyId} />
          </div>
        )}
      </div>
    </div>
  );
}
