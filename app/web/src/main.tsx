import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/api/client";
import { createAccess } from "@/app/access";
import { App } from "@/app/App";
import { createConnection } from "@/lib/connection";
import { readLaunch } from "@/lib/launch";
import "@/styles/tokens.css";
import "@/styles/shared.css";
import "@/styles/app.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Missing #root element");
}

const launch = readLaunch();
const access = createAccess({ launch });
const api = createApiClient({ access, connection: createConnection() });
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

// start() strips the code from the hash before the first render, so the router never sees it.
void access.start();

createRoot(container).render(
  <StrictMode>
    <App api={api} queryClient={queryClient} launch={launch} />
  </StrictMode>,
);
