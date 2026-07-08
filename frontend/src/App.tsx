import { useState } from "react";

import { DetailPane } from "./components/DetailPane";
import { PolicyList } from "./components/PolicyList";
import { ProviderSidebar } from "./components/ProviderSidebar";
import { TopBar } from "./components/TopBar";
import type { Provider } from "./api/types";

export default function App() {
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);

  function handleSelectProvider(provider: Provider) {
    setSelectedProvider(provider);
    setSelectedPolicyId(null);
  }

  function handleProviderDeleted(id: string) {
    if (id === selectedProvider?.id) {
      setSelectedProvider(null);
      setSelectedPolicyId(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar onProviderCreated={handleSelectProvider} />
      <div className="flex flex-1 overflow-hidden">
        <ProviderSidebar
          selectedId={selectedProvider?.id ?? null}
          onSelect={handleSelectProvider}
          onDeleted={handleProviderDeleted}
        />
        <main className="flex flex-1 overflow-hidden bg-zinc-50 dark:bg-zinc-950">
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
