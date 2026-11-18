import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// One cache for the whole app: created here, outside any component, so it survives re-renders.
const queryClient = new QueryClient();

const root = document.getElementById("root");
if (!root) throw new Error("Falta el elemento #root en index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
