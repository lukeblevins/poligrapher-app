import type { ReactNode } from "react";
import type { GraphStatsData } from "../api/types";
import { useStats } from "../hooks/queries";

export function StatsPanel({ policyId }: { policyId: string }) {
  const { data, isLoading, isError, error } = useStats(policyId);

  if (isLoading) return <p role="status" className="quiet-state">Loading graph statistics…</p>;
  if (isError) return <p role="alert" className="status-error">Could not load graph statistics. {error instanceof Error ? error.message : "Try again."}</p>;
  if (!data?.stats) return <p className="quiet-state">Graph statistics are not available for this analysis.</p>;

  const stats = data.stats;
  return (
    <div className="m3-results-panel">
      <header className="m3-results-heading">
        <p className="section-kicker">Policy graph</p>
        <h2>Graph overview</h2>
        <p>Structure and connectivity for this policy snapshot.</p>
      </header>
      <section aria-label="Graph overview" className="m3-metric-grid">
        <Metric label="Nodes" value={stats.node_count} prominent />
        <Metric label="Connections" value={stats.edge_count} prominent />
        <Metric label="Components" value={stats.component_count} />
        <Metric label="Density" value={stats.density.toFixed(4)} />
        <Metric label="Clustering" value={stats.average_clustering.toFixed(4)} />
        <Metric label="Transitivity" value={stats.transitivity.toFixed(4)} />
        <Metric label="Isolated nodes" value={stats.isolated_nodes} />
        <Metric label="Self-loops" value={stats.self_loop_count} />
        <Metric label="Largest component" value={`${stats.largest_component_size} · ${(stats.largest_component_ratio * 100).toFixed(0)}%`} />
      </section>
      <ResultSection title="Graph composition">
        <CountList title="Node types" counts={stats.node_type_counts} />
        <CountList title="Relationship types" counts={stats.edge_type_counts} />
      </ResultSection>
      <ResultSection title="Connectivity">
        <DegreeTable stats={stats} />
      </ResultSection>
      <ResultSection title="Most connected concepts">
        <HubList nodes={stats.top_degree_nodes} />
      </ResultSection>
    </div>
  );
}

function Metric({ label, value, prominent = false }: { label: string; value: number | string; prominent?: boolean }) {
  return <article className={`m3-metric-card${prominent ? " m3-metric-card-prominent" : ""}`}><p>{label}</p><strong className="data-value">{value}</strong></article>;
}

function ResultSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="m3-result-section"><h3>{title}</h3>{children}</section>;
}

function CountList({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((left, right) => right[1] - left[1]);
  if (!entries.length) return null;
  return <div className="m3-count-list"><h4>{title}</h4><div>{entries.map(([name, count]) => <span key={name} className="m3-data-chip"><b>{name}</b><em className="data-value">{count}</em></span>)}</div></div>;
}

function DegreeTable({ stats }: { stats: GraphStatsData }) {
  const rows: [string, GraphStatsData["degree"]][] = [["Total degree", stats.degree], ["Incoming degree", stats.in_degree], ["Outgoing degree", stats.out_degree]];
  return <div className="m3-stat-table-wrap"><table className="m3-stat-table"><thead><tr><th scope="col">Measure</th><th scope="col">Minimum</th><th scope="col">Maximum</th><th scope="col">Average</th><th scope="col">Median</th></tr></thead><tbody>{rows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value.min}</td><td>{value.max}</td><td>{value.mean.toFixed(2)}</td><td>{value.median.toFixed(2)}</td></tr>)}</tbody></table></div>;
}

function HubList({ nodes }: { nodes: [string, number][] }) {
  if (!nodes?.length) return <p className="m3-supporting-copy">No high-connectivity concepts were recorded.</p>;
  return <ol className="m3-hub-list">{nodes.slice(0, 8).map(([node, degree], index) => <li key={node}><span>{index + 1}</span><b>{node}</b><em className="data-value">{degree}</em></li>)}</ol>;
}
