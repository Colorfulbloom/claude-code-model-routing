/* Mounts the real route tree over a fake server, for the shell and page tests. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { ApiContext, createApiClient } from "@/api/client";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import type { Access } from "@/app/access";
import { StatusRegion } from "@/app/harness";
import { createAppRouter } from "@/app/router";
import { FakeChannel } from "@/app/test-channel";
import { createConnection } from "@/lib/connection";
import { setViewport } from "@/test/media";
import { fakeServer, INSTANCE } from "@/test/server";
import type { FakeServer } from "@/test/server";

export interface MountOptions {
  launchProject?: string | null;
  width?: number;
  server?: FakeServer;
}

export async function mount(hash: string, options: MountOptions = {}) {
  const { launchProject = null, width = 1440, server = fakeServer() } = options;
  setViewport(width);
  sessionStorage.clear();
  FakeChannel.reset();
  sessionStorage.setItem(STORAGE_KEYS.readKey, "key-1");
  sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
  if (launchProject !== null) sessionStorage.setItem(STORAGE_KEYS.project, launchProject);
  history.replaceState(null, "", hash);
  const access: Access = createAccess({
    launch: { nonce: "", instance: INSTANCE, command: "/bartab-preview" },
    makeChannel: () => new FakeChannel("bartab-access").asChannel(),
  });
  await access.start();
  const connection = createConnection();
  const api = createApiClient({ access, connection, fetchFn: server.fetch });
  const router = createAppRouter(access);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ApiContext value={api}>
        <StatusRegion />
        <RouterProvider router={router} />
      </ApiContext>
    </QueryClientProvider>,
  );
  return { access, connection, router, server, api };
}
