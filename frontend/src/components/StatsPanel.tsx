import type { GraphStatsData } from "../api/types";
import { useStats } from "../hooks/queries";

export function StatsPanel({ policyId }: { policyId: string }) {
  const { data, isLoading, isError } = useStats(policyId);

  if (isLoading) return <p className="text-sm text-zinc-400">Loading…</p>;
  if (isError || !data?.stats)
    return <p className="text-sm text-zinc-400">No graph statistics available.</p>;

  const s = data.stats;
  return (
    <div className="space-y-4 text-sm">
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
    <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800/50">
      <div className="text-xs text-zinc-500 dark:text-zinc-400">{label}</div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  );
}

function CountSection({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
        {title}
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([name, count]) => (
          <span
            key={name}
            className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800"
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
      <h3 className="mb-1 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
        Degree
      </h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-zinc-400">
            <th className="py-1 font-medium"></th>
            <th className="py-1 font-medium">min</th>
            <th className="py-1 font-medium">max</th>
            <th className="py-1 font-medium">mean</th>
            <th className="py-1 font-medium">median</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map(([label, d]) => (
            <tr key={label} className="border-t border-zinc-100 dark:border-zinc-800">
              <td className="py-1 font-sans text-zinc-500">{label}</td>
              <td className="py-1">{d.min}</td>
              <td className="py-1">{d.max}</td>
              <td className="py-1">{d.mean.toFixed(2)}</td>
              <td className="py-1">{d.median.toFixed(2)}</td>
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
      <h3 className="mb-1 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
        {title}
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {nodes.slice(0, 8).map(([node, deg]) => (
          <span
            key={node}
            className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800"
          >
            {node} ({deg})
          </span>
        ))}
      </div>
    </div>
  );
}
