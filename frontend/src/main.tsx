import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource-variable/roboto";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";
import { initializeTheme } from "./hooks/useTheme";

initializeTheme();

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
