import { useState } from "react";

import { DetailPane } from "./components/DetailPane";
import { PolicyList } from "./components/PolicyList";
import { ProviderSidebar } from "./components/ProviderSidebar";
import { TopBar } from "./components/TopBar";
import type { Provider } from "./api/types";
import { useProviders } from "./hooks/queries";

export default function App() {
  const { data: providers = [] } = useProviders();
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
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

  return (
    <div className="flex h-full flex-col">
      <TopBar onProviderCreated={handleSelectProvider} />
      <div className="flex flex-1 overflow-hidden">
        <ProviderSidebar
          selectedId={selectedProviderId}
          onSelect={handleSelectProvider}
          onDeleted={handleProviderDeleted}
        />
        <main className="flex flex-1 overflow-hidden bg-slate-50 dark:bg-slate-950">
          <PolicyList
            provider={selectedProvider}
            selectedPolicyId={selectedPolicyId}
            onSelectPolicy={setSelectedPolicyId}
          />
          {selectedPolicyId && (
            <DetailPane
              policyId={selectedPolicyId}
              onClose={() => setSelectedPolicyId(null)}
            />
          )}
        </main>
      </div>
    </div>
  );
}
