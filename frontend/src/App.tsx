import { lazy, Suspense, useState } from "react";

import { PolicyList } from "./components/PolicyList";
import { ProviderSidebar } from "./components/ProviderSidebar";
import { TopBar } from "./components/TopBar";
import { TooltipProvider } from "./components/Tooltip";
import type { Provider, TaskStatus } from "./api/types";
import { useProviders } from "./hooks/queries";

const DetailPane = lazy(() => import("./components/DetailPane").then((module) => ({ default: module.DetailPane })));

export default function App() {
  const { data: providers = [] } = useProviders();
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [historyTarget, setHistoryTarget] = useState<{ taskId: string; nonce: number } | null>(null);
  const selectedProvider = providers.find((provider) => provider.id === selectedProviderId) ?? null;

  function handleSelectProvider(provider: Provider) {
    setSelectedProviderId(provider.id);
    setSelectedPolicyId(null);
  }

  function handleProviderDeleted(id: string) {
    if (id === selectedProviderId) {
      setSelectedProviderId(null);
      setSelectedPolicyId(null);
    }
  }

  function handleBackToCompanies() {
    setSelectedProviderId(null);
    setSelectedPolicyId(null);
  }

  function handleViewRun(task: TaskStatus) {
    if (!task.provider_id || !providers.some((provider) => provider.id === task.provider_id)) return;
    setSelectedProviderId(task.provider_id);
    setSelectedPolicyId(null);
    setHistoryTarget({ taskId: task.task_id, nonce: Date.now() });
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
        <TopBar onProviderCreated={handleSelectProvider} onViewRun={handleViewRun} />
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <ProviderSidebar
            selectedId={selectedProviderId}
            onSelect={handleSelectProvider}
            onDeleted={handleProviderDeleted}
            mobileHidden={Boolean(selectedProvider)}
          />
          <main className={`${selectedProvider ? "flex" : "hidden md:flex"} min-w-0 flex-1 overflow-hidden bg-slate-50 dark:bg-slate-950`}>
            <PolicyList
              provider={selectedProvider}
              selectedPolicyId={selectedPolicyId}
              onSelectPolicy={setSelectedPolicyId}
              onBack={handleBackToCompanies}
              historyTargetTaskId={historyTarget?.taskId ?? null}
              historyTargetNonce={historyTarget?.nonce}
            />
            {selectedPolicyId && (
              <Suspense fallback={<div role="status" className="flex flex-1 items-center justify-center p-6 text-sm text-slate-500">Loading analysis details…</div>}>
                <DetailPane
                  policyId={selectedPolicyId}
                  onClose={() => setSelectedPolicyId(null)}
                />
              </Suspense>
            )}
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
