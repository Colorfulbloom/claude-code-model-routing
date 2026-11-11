/* Mounts the real route tree over a fake server, for the shell and page tests. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { ApiContext, createApiClient } from "@/api/client";
import { createEditClient, EditContext } from "@/api/edit";
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
  /** Edit keys by project key, as the launch link hands them over. None means the page has none. */
  editKeys?: Record<string, string>;
}

/** The edit client only listens on its channel and never posts, so a bare event target does. */
class QuietChannel extends EventTarget {
  postMessage(): void {
    /* the edit client only listens */
  }
  close(): void {
    /* nothing to close */
  }
}

export async function mount(hash: string, options: MountOptions = {}) {
  const { launchProject = null, width = 1440, server = fakeServer(), editKeys } = options;
  setViewport(width);
  sessionStorage.clear();
  FakeChannel.reset();
  sessionStorage.setItem(STORAGE_KEYS.readKey, "key-1");
  sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
  if (editKeys !== undefined) {
    sessionStorage.setItem(STORAGE_KEYS.editKeys, JSON.stringify(editKeys));
  }
  if (launchProject !== null) sessionStorage.setItem(STORAGE_KEYS.project, launchProject);
  history.replaceState(null, "", hash);
  const access: Access = createAccess({
    launch: { nonce: "", instance: INSTANCE, command: "/bartab-preview" },
    makeChannel: () => new FakeChannel("bartab-access").asChannel(),
  });
  await access.start();
  const connection = createConnection();
  const api = createApiClient({ access, connection, fetchFn: server.fetch });
  // The edit client reads through the same fake, with the page's own keys and no real channel.
  const edit = createEditClient({
    access,
    connection,
    fetchFn: server.fetch,
    instance: INSTANCE,
    makeChannel: () => new QuietChannel() as unknown as BroadcastChannel,
  });
  const router = createAppRouter(access);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ApiContext value={api}>
        <EditContext value={edit}>
          <StatusRegion />
          <RouterProvider router={router} />
        </EditContext>
      </ApiContext>
    </QueryClientProvider>,
  );
  return { access, connection, router, server, api, edit };
}
