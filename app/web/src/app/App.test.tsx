import { QueryClient } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createApiClient } from "@/api/client";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { App } from "@/app/App";
import { postStatus } from "@/app/harness";
import { FakeChannel } from "@/app/test-channel";
import { createConnection } from "@/lib/connection";
import { resetViewport } from "@/test/media";
import { appInfo, fakeServer, INSTANCE } from "@/test/server";
import type { FakeServer } from "@/test/server";

const launch = { nonce: "", instance: INSTANCE, command: "/bartab-preview" };

function setup(server: FakeServer = fakeServer()) {
  const access = createAccess({
    launch,
    makeChannel: () => new FakeChannel("bartab-access").asChannel(),
  });
  const connection = createConnection();
  const api = createApiClient({ access, connection, fetchFn: server.fetch });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<App api={api} queryClient={queryClient} launch={launch} />);
  return { access, connection, server, queryClient };
}

function unlockedTab(): void {
  sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
  sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
}

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  sessionStorage.clear();
  FakeChannel.reset();
  postStatus("");
  history.replaceState(null, "", "#/p/builder/live");
});

describe("App gate", () => {
  it("shows a brand-only hold, then the locked page when no tab answers", async () => {
    const { access } = setup();
    await act(() => access.start());
    expect(screen.getByText("Bar Tab")).toBeInTheDocument();
    expect(screen.getByText("Checking for another dashboard tab")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: "This tab can't reach the dashboard",
    });
    expect(heading).toHaveFocus();
    expect(screen.getByText(/opened without a code/)).toBeInTheDocument();
    expect(document.title).toBe("Can't reach the dashboard, Bar Tab");
  });

  it("renders the shell on the route when the tab holds a key", async () => {
    unlockedTab();
    const { access } = setup();
    await act(() => access.start());
    expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("shows first run while the first ingest is not done, then opens the launch project's Live", async () => {
    unlockedTab();
    sessionStorage.setItem(STORAGE_KEYS.project, "builder");
    history.replaceState(null, "", "#/");
    const server = fakeServer({
      app: appInfo({
        ingest: {
          state: "running",
          files_done: 312,
          files_total: 1240,
          bytes_done: 1_200_000_000,
          bytes_total: 2_000_000_000,
          error: null,
          retrying: false,
          retry_at: null,
        },
      }),
    });
    const { access } = setup(server);
    await act(() => access.start());
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: "Getting the dashboard ready",
    });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "1.2 of 2.0 GB");
    expect(screen.queryByRole("navigation")).toBeNull();
    server.app = appInfo();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1100));
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/p/builder/live");
  });

  it("never flashes first run for a store with no transcripts", async () => {
    unlockedTab();
    sessionStorage.setItem(STORAGE_KEYS.project, "builder");
    history.replaceState(null, "", "#/");
    // The server fixes the totals at zero files once it has listed the folder, so the page
    // sees "waiting" and "running" with zero files, then done.
    const waiting = appInfo({
      ingest: { ...appInfo().ingest, state: "waiting", files_total: 0, bytes_total: 0 },
    });
    const zeroFiles = appInfo({ ingest: { ...appInfo().ingest, state: "running" } });
    const server = fakeServer({ app: waiting });
    const { access, queryClient } = setup(server);
    const seen: string[] = [];
    const watch = new MutationObserver(() => {
      if ((document.body.textContent ?? "").includes("Counting files")) seen.push("flash");
    });
    watch.observe(document.body, { subtree: true, childList: true, characterData: true });
    try {
      await act(() => access.start());
      await waitFor(() => expect(server.calls.some((c) => c.startsWith("/api/app"))).toBe(true));
      expect(screen.queryByText("Counting files")).toBeNull();
      server.app = zeroFiles;
      await act(() => queryClient.refetchQueries({ queryKey: ["app"] }));
      expect(screen.queryByText("Counting files")).toBeNull();
      server.app = appInfo();
      await act(() => queryClient.refetchQueries({ queryKey: ["app"] }));
      expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    } finally {
      watch.disconnect();
    }
    expect(seen).toEqual([]);
    expect(screen.queryByText("Getting the dashboard ready")).toBeNull();
  });

  it("shows the stopped page when the server stops answering", async () => {
    unlockedTab();
    const server = fakeServer();
    const { access } = setup(server);
    await act(() => access.start());
    await screen.findByRole("heading", { level: 1, name: "Live" });
    act(() => {
      access.setStopped();
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "The dashboard stopped answering" }),
    ).toBeInTheDocument();
    expect(document.title).toBe("Dashboard stopped answering, Bar Tab");
  });
});
