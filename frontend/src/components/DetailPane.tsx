import { useId, useState } from "react";

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
  const tabsId = useId();

  const selectAdjacentTab = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = TABS.findIndex((item) => item.id === tab);
    const nextIndex = event.key === "Home" ? 0
      : event.key === "End" ? TABS.length - 1
        : event.key === "ArrowRight" ? (currentIndex + 1) % TABS.length
          : (currentIndex - 1 + TABS.length) % TABS.length;
    const nextTab = TABS[nextIndex].id;
    setTab(nextTab);
    event.currentTarget.querySelector<HTMLButtonElement>(`#${CSS.escape(`${tabsId}-${nextTab}`)}`)?.focus();
  };

  return (
    <div
      className="flex w-full flex-shrink-0 flex-col border-l border-slate-300 bg-white xl:w-[52%] dark:border-slate-800 dark:bg-slate-900"
      aria-label="Analysis details"
    >
      <div className="flex flex-shrink-0 items-stretch justify-between border-b border-slate-300 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <div role="tablist" aria-label="Analysis views" className="flex min-w-0" onKeyDown={selectAdjacentTab}>
          {TABS.map((t) => (
            <button
              key={t.id}
              id={`${tabsId}-${t.id}`}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`${tabsId}-panel`}
              tabIndex={tab === t.id ? 0 : -1}
              className={`flex min-h-12 min-w-0 items-center gap-1.5 border-r border-slate-300 px-3 py-3 text-xs font-semibold transition-colors sm:gap-2 sm:px-4 first:border-l dark:border-slate-800 ${
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
          className="icon-button my-auto mr-1.5 sm:mr-3"
          onClick={onClose}
          aria-label="Close analysis details"
        >
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4" aria-hidden="true">
            <path className="xl:hidden" d="m12 5-5 5 5 5" strokeLinecap="round" strokeLinejoin="round" />
            <path className="hidden xl:block" d="m5 5 10 10M15 5 5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div
        id={`${tabsId}-panel`}
        role="tabpanel"
        aria-labelledby={`${tabsId}-${tab}`}
        tabIndex={0}
        className="min-h-0 flex-1 overflow-hidden focus-visible:ring-inset"
      >
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
