import { lazy, Suspense, useState } from "react";

import { PolicyList } from "./components/PolicyList";
import { ProviderSidebar } from "./components/ProviderSidebar";
import { CollectionsWorkspace } from "./components/CollectionsWorkspace";
import { ScheduledWorkspace } from "./components/ScheduledWorkspace";
import { TopBar } from "./components/TopBar";
import { GlobalNavigationRail } from "./components/GlobalNavigationRail";
import { TooltipProvider } from "./components/Tooltip";
import { AddProviderModal } from "./components/modals/AddProviderModal";
import { AboutWorkspace } from "./components/AboutWorkspace";
import type { Policy, Provider, TaskStatus } from "./api/types";
import { useProviders } from "./hooks/queries";

const DetailPane = lazy(() => import("./components/DetailPane").then((module) => ({ default: module.DetailPane })));

export default function App() {
  const [workspace, setWorkspace] = useState<"companies" | "collections" | "scheduled" | "about">("companies");
  const { data: providers = [] } = useProviders();
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [historyTarget, setHistoryTarget] = useState<{ taskId: string; nonce: number } | null>(null);
  const selectedProvider = providers.find((provider) => provider.id === selectedProviderId) ?? null;

  function handleSelectProvider(provider: Provider) {
    setWorkspace("companies");
    setSelectedProviderId(provider.id);
    setSelectedPolicy(null);
  }

  function handleProviderDeleted(id: string) {
    if (id === selectedProviderId) {
      setSelectedProviderId(null);
      setSelectedPolicy(null);
    }
  }

  function handleBackToCompanies() {
    setSelectedProviderId(null);
    setSelectedPolicy(null);
  }

  function handleViewRun(task: TaskStatus) {
    if (!task.provider_id || !providers.some((provider) => provider.id === task.provider_id)) return;
    setSelectedProviderId(task.provider_id);
    setSelectedPolicy(null);
    setHistoryTarget({ taskId: task.task_id, nonce: Date.now() });
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh min-h-0 overflow-hidden">
        <GlobalNavigationRail
          workspace={workspace}
          onWorkspaceChange={setWorkspace}
          onAddCompany={() => setShowAddProvider(true)}
        />
        <div className="m3-app-content flex min-w-0 flex-1 flex-col overflow-hidden pb-16 sm:pb-0">
        <TopBar
          workspace={workspace}
          onAddCompany={() => setShowAddProvider(true)}
          onViewRun={handleViewRun}
        />
        {workspace === "about" ? <AboutWorkspace /> : workspace === "collections" ? <CollectionsWorkspace /> : workspace === "scheduled" ? <ScheduledWorkspace /> : (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <ProviderSidebar
            selectedId={selectedProviderId}
            onSelect={handleSelectProvider}
            onDeleted={handleProviderDeleted}
            mobileHidden={Boolean(selectedProvider)}
          />
          <main className={`${selectedProvider ? "flex" : "hidden lg:flex"} m3-company-workspace m3-detail-pane min-w-0 flex-1 overflow-hidden`}>
            <PolicyList
              provider={selectedProvider}
              selectedPolicyId={selectedPolicy?.id ?? null}
              onSelectPolicy={setSelectedPolicy}
              onBack={handleBackToCompanies}
              historyTargetTaskId={historyTarget?.taskId ?? null}
              historyTargetNonce={historyTarget?.nonce}
            />
            {selectedPolicy && <>
              <button type="button" className="m3-analysis-scrim" aria-label="Close analysis details" onClick={() => setSelectedPolicy(null)} />
              <Suspense fallback={<div role="dialog" aria-modal="true" aria-label="Analysis details" className="m3-analysis-sheet flex items-center justify-center p-6 text-sm text-[var(--md-sys-color-on-surface-variant)]">Loading analysis details…</div>}>
                <DetailPane
                  policy={selectedPolicy}
                  providerName={selectedProvider?.name ?? "Company"}
                  onClose={() => setSelectedPolicy(null)}
                />
              </Suspense>
            </>}
          </main>
        </div>
        )}
        </div>
        {showAddProvider && (
          <AddProviderModal
            onClose={() => setShowAddProvider(false)}
            onCreated={(provider) => {
              setShowAddProvider(false);
              handleSelectProvider(provider);
            }}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
