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

export function DetailPane({ policyId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("graph");

  return (
    <div
      className="flex flex-shrink-0 flex-col border-l border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900"
      style={{ width: "52%" }}
    >
      <div className="flex flex-shrink-0 items-center justify-between border-b border-zinc-100 px-3 pt-2 dark:border-zinc-800">
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab-btn text-xs ${tab === t.id ? "tab-active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          className="pb-2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          onClick={onClose}
          aria-label="Close panel"
        >
          ✕
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "graph" && (
          <div className="h-full p-2">
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
