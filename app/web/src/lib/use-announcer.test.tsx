import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveFeed } from "@/api/live";
import type { Timeline } from "@/api/types";
import { run, timeline, NOW } from "@/test/timelines";
import { useAnnouncer } from "@/lib/use-announcer";

const said = vi.hoisted(() => vi.fn<(text: string) => void>());
vi.mock("@/app/harness", () => ({ postStatus: said }));

const at = (seconds: number): number => Date.parse(NOW) + seconds * 1000;

function feedOf(answer: Timeline, seconds: number): LiveFeed<Timeline> {
  return { answer, serverMs: at(seconds), receivedAt: at(seconds) };
}

const scout = (state: "working" | "finished") =>
  run("scout-1", { agent: "scout", dispatch_order: 1, state });

function answer(seconds: number, runs: Timeline["runs"], etag: string): Timeline {
  return { ...timeline({ runs }), etag, server_time: new Date(at(seconds)).toISOString() };
}

describe("useAnnouncer", () => {
  beforeEach(() => {
    said.mockClear();
  });

  it("treats the first answer after Resume as a baseline, like a return from a hidden tab", () => {
    const first = answer(0, [run("main")], "a");
    const { rerender } = renderHook(
      ({ feed, active }) => {
        useAnnouncer(feed, active);
      },
      { initialProps: { feed: feedOf(first, 0), active: true } },
    );
    // Pause: polling stops, the answer stays.
    rerender({ feed: feedOf(first, 0), active: false });
    // Resume: the first answer is a baseline even though a run started while paused.
    const resumed = answer(120, [run("main"), scout("working")], "b");
    rerender({ feed: feedOf(resumed, 120), active: true });
    expect(said).not.toHaveBeenCalled();
    // The next change speaks.
    const done = answer(125, [run("main"), scout("finished")], "c");
    rerender({ feed: feedOf(done, 125), active: true });
    expect(said).toHaveBeenCalledWith("scout finished");
  });

  it("speaks a held finish on the first poll after the minute, even when it answers unchanged", () => {
    const base = answer(0, [run("main")], "a");
    const { rerender } = renderHook(
      ({ feed }) => {
        useAnnouncer(feed, true);
      },
      { initialProps: { feed: feedOf(base, 0) } },
    );
    const started = answer(5, [run("main"), scout("working")], "b");
    rerender({ feed: feedOf(started, 5) });
    expect(said).toHaveBeenLastCalledWith("scout started by Main session");
    const finished = answer(20, [run("main"), scout("finished")], "c");
    rerender({ feed: feedOf(finished, 20) });
    expect(said).toHaveBeenCalledTimes(1);
    // Same answer object, later time: an unchanged poll.
    act(() => {
      rerender({ feed: feedOf(finished, 40) });
    });
    expect(said).toHaveBeenCalledTimes(1);
    rerender({ feed: feedOf(finished, 66) });
    expect(said).toHaveBeenCalledTimes(2);
    expect(said).toHaveBeenLastCalledWith("scout finished");
    rerender({ feed: feedOf(finished, 70) });
    expect(said).toHaveBeenCalledTimes(2);
  });
});
