import { useState } from "react";

import type { Provider } from "../api/types";
import { useDeleteProvider, useProviders } from "../hooks/queries";

interface Props {
  selectedId: string | null;
  onSelect: (provider: Provider) => void;
  onDeleted?: (id: string) => void;
}

function statusColor(p: Provider): string {
  if (p.policy_count === 0) return "bg-zinc-300 dark:bg-zinc-600";
  if (p.succeeded_count > 0) return "bg-green-500";
  if (p.failed_count === p.policy_count) return "bg-red-500";
  return "bg-amber-400";
}

export function ProviderSidebar({ selectedId, onSelect, onDeleted }: Props) {
  const { data: providers = [], isLoading } = useProviders();
  const deleteProvider = useDeleteProvider();
  const [query, setQuery] = useState("");

  const filtered = providers.filter((p) =>
    p.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <aside className="flex w-72 flex-shrink-0 flex-col border-r border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900">
      <div className="border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <input
          type="search"
          className="form-input"
          placeholder="Search companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-sm text-zinc-400">Loading…</p>}
        {!isLoading && filtered.length === 0 && (
          <p className="p-4 text-sm text-zinc-400">No companies.</p>
        )}
        {filtered.map((p) => (
          <div
            key={p.id}
            onClick={() => onSelect(p)}
            className={`group flex cursor-pointer items-center gap-2 border-b border-zinc-50 px-4 py-2.5 text-sm dark:border-zinc-800/50 ${
              selectedId === p.id
                ? "bg-indigo-50 font-medium dark:bg-indigo-950"
                : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
            }`}
          >
            <span className={`h-2 w-2 flex-shrink-0 rounded-full ${statusColor(p)}`} />
            <div className="min-w-0 flex-1">
              <div className="truncate">{p.name}</div>
              <div className="truncate text-xs text-zinc-400 dark:text-zinc-500">
                {p.industry ?? "—"} · {p.policy_count} policies
              </div>
            </div>
            <button
              className="hidden text-xs text-zinc-400 hover:text-red-500 group-hover:block"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete provider "${p.name}" and all its policies?`)) {
                  deleteProvider.mutate(p.id, {
                    onSuccess: () => onDeleted?.(p.id),
                  });
                }
              }}
              aria-label={`Delete ${p.name}`}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
