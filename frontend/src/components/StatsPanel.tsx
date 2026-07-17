import type { GraphStatsData } from "../api/types";
import { useStats } from "../hooks/queries";

export function StatsPanel({ policyId }: { policyId: string }) {
  const { data, isLoading, isError, error } = useStats(policyId);

  if (isLoading) return <p role="status" className="quiet-state">Loading graph statistics…</p>;
  if (isError) return <p role="alert" className="status-error">Could not load graph statistics. {error instanceof Error ? error.message : "Try again."}</p>;
  if (!data?.stats) return <p className="quiet-state">No graph statistics are available for this analysis.</p>;

  const s = data.stats;
  return (
    <div className="space-y-6 text-sm">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Nodes" value={s.node_count} />
        <Metric label="Edges" value={s.edge_count} />
        <Metric label="Components" value={s.component_count} />
        <Metric label="Density" value={s.density.toFixed(4)} />
        <Metric label="Clustering" value={s.average_clustering.toFixed(4)} />
        <Metric label="Transitivity" value={s.transitivity.toFixed(4)} />
        <Metric label="Isolated nodes" value={s.isolated_nodes} />
        <Metric label="Self-loops" value={s.self_loop_count} />
        <Metric
          label="Largest component"
          value={`${s.largest_component_size} (${(s.largest_component_ratio * 100).toFixed(0)}%)`}
        />
      </div>

      <CountSection title="Node types" counts={s.node_type_counts} />
      <CountSection title="Edge types" counts={s.edge_type_counts} />
      <DegreeSection s={s} />
      <HubSection title="Top hubs (degree)" nodes={s.top_degree_nodes} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-slate-300 bg-slate-50/70 px-3.5 py-3 dark:border-slate-700 dark:bg-slate-800/50">
      <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{label}</div>
      <div className="data-value mt-1 text-base font-semibold text-slate-900 dark:text-white">{value}</div>
    </div>
  );
}

function CountSection({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div>
      <h3 className="section-kicker mb-2">
        {title}
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([name, count]) => (
          <span
            key={name}
            className="data-value rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            {name}: {count}
          </span>
        ))}
      </div>
    </div>
  );
}

function DegreeSection({ s }: { s: GraphStatsData }) {
  const rows: [string, GraphStatsData["degree"]][] = [
    ["Degree", s.degree],
    ["In-degree", s.in_degree],
    ["Out-degree", s.out_degree],
  ];
  return (
    <div>
      <h3 className="section-kicker mb-2">
        Degree
      </h3>
      <table className="w-full overflow-hidden rounded-lg text-xs tabular-nums">
        <thead>
          <tr className="text-left text-slate-500 dark:text-slate-400">
            <th className="py-1 font-medium"></th>
            <th className="py-1 font-medium">min</th>
            <th className="py-1 font-medium">max</th>
            <th className="py-1 font-medium">mean</th>
            <th className="py-1 font-medium">median</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map(([label, d]) => (
            <tr key={label} className="border-t border-slate-100 dark:border-slate-800">
              <td className="py-2 font-sans font-medium text-slate-500">{label}</td>
              <td className="py-2">{d.min}</td>
              <td className="py-2">{d.max}</td>
              <td className="py-2">{d.mean.toFixed(2)}</td>
              <td className="py-2">{d.median.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HubSection({ title, nodes }: { title: string; nodes: [string, number][] }) {
  if (!nodes?.length) return null;
  return (
    <div>
      <h3 className="section-kicker mb-2">
        {title}
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {nodes.slice(0, 8).map(([node, deg]) => (
          <span
            key={node}
            className="data-value rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            {node} ({deg})
          </span>
        ))}
      </div>
    </div>
  );
}
