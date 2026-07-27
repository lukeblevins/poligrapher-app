import { useId, useState, type CSSProperties } from "react";
import assessmentsIcon from "@material-symbols/svg-400/rounded/fact_check.svg?url";
import closeIcon from "@material-symbols/svg-400/rounded/close.svg?url";
import graphIcon from "@material-symbols/svg-400/rounded/account_tree.svg?url";
import statsIcon from "@material-symbols/svg-400/rounded/bar_chart.svg?url";

import { AssessmentsPanel } from "./AssessmentsPanel";
import { GraphViewer } from "./GraphViewer";
import { StatsPanel } from "./StatsPanel";
import type { Policy } from "../api/types";

type Tab = "graph" | "stats" | "assessments";

interface Props {
  policy: Policy;
  providerName: string;
  onClose: () => void;
}

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "graph", label: "Graph", icon: graphIcon },
  { id: "stats", label: "Statistics", icon: statsIcon },
  { id: "assessments", label: "Assessments", icon: assessmentsIcon },
];

function MaterialSymbol({ src }: { src: string }) {
  return <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

function analysisMethod(policy: Policy) {
  if (policy.method === "pdf_upload") return "Uploaded policy PDF";
  if (policy.method === "pdf_from_page") return "Policy page PDF";
  return "Live policy page";
}

function analysisStatus(policy: Policy) {
  if (policy.pipeline_status === "succeeded") return { label: "Complete", tone: "success" };
  if (policy.pipeline_status === "failed") return { label: "Incomplete", tone: "error" };
  return { label: "In progress", tone: "primary" };
}

function snapshotDate(policy: Policy) {
  const value = policy.capture_date ? `${policy.capture_date}T00:00:00` : policy.created_at;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function DetailPane({ policy, providerName, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("graph");
  const tabsId = useId();
  const status = analysisStatus(policy);

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
      className="m3-analysis-detail m3-analysis-sheet flex flex-shrink-0 flex-col"
      role="dialog"
      aria-modal="true"
      aria-label="Analysis details"
    >
      <header className="m3-analysis-report-header">
        <div className="min-w-0">
          <p className="section-kicker">Policy analysis report</p>
          <h2 className="truncate">{providerName}</h2>
          <p>{analysisMethod(policy)} · Snapshot {snapshotDate(policy)}</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          <span className={`m3-analysis-run-status m3-status-${status.tone}`}>{status.label}</span>
          <button
            className="m3-analysis-close"
            onClick={onClose}
            aria-label="Close analysis details"
          >
            <MaterialSymbol src={closeIcon} />
          </button>
        </div>
      </header>

      <div className="m3-analysis-viewbar flex flex-shrink-0 items-center">
        <div role="tablist" aria-label="Analysis views" className="m3-analysis-tabs" onKeyDown={selectAdjacentTab}>
          {TABS.map((t) => (
            <button
              key={t.id}
              id={`${tabsId}-${t.id}`}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`${tabsId}-panel`}
              tabIndex={tab === t.id ? 0 : -1}
              className={`m3-analysis-tab ${
                tab === t.id
                  ? "m3-analysis-tab-selected"
                  : ""
              }`}
              onClick={() => setTab(t.id)}
            >
              <MaterialSymbol src={t.icon} />
              {t.label}
            </button>
          ))}
        </div>
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
            <GraphViewer key={policy.id} policyId={policy.id} />
          </div>
        )}
        {tab === "stats" && (
          <div className="m3-analysis-panel h-full overflow-auto">
            <StatsPanel policyId={policy.id} />
          </div>
        )}
        {tab === "assessments" && (
          <div className="m3-analysis-panel h-full overflow-auto">
            <AssessmentsPanel policyId={policy.id} />
          </div>
        )}
      </div>
    </div>
  );
}
