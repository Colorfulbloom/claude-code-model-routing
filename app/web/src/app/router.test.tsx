import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
  document.title = "";
});

const routes: [string, string][] = [
  ["#/p/builder/live", "Live"],
  ["#/p/builder/review/summary?range=30d", "Summary"],
  ["#/p/builder/review/sessions", "Sessions"],
  ["#/p/builder/review/sessions/s1", "Session"],
  ["#/p/builder/review/agents", "Agents"],
  ["#/p/builder/review/agents/new", "New agent"],
  ["#/p/builder/review/agents/reviewer/edit", "Edit agent"],
  ["#/p/builder/review/models", "Models"],
  ["#/p/builder/setup", "Your setup"],
  ["#/p/builder/setup/settings/effort", "Setup item"],
  ["#/p/builder/setup/settings/effort/edit", "Edit setup item"],
  ["#/p/builder/to-fix", "To fix"],
  ["#/reference/decides", "How Claude Code decides"],
  ["#/reference/glossary", "Glossary"],
];

describe("routes", () => {
  it.each(routes)("%s renders the h1 %s, focuses it and announces it", async (hash, name) => {
    await mount(hash);
    const heading = await screen.findByRole("heading", { level: 1, name });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent(name);
    expect(screen.getByText("This page comes in a later release.")).toBeInTheDocument();
    const withProject = hash.startsWith("#/p/");
    await waitFor(() => {
      expect(document.title).toBe(withProject ? `${name}, Builder, Bar Tab` : `${name}, Bar Tab`);
    });
  });

  it("renders More at phone width with its own page", async () => {
    await mount("#/more", { width: 375 });
    const heading = await screen.findByRole("heading", { level: 1, name: "More" });
    expect(heading).toHaveFocus();
    expect(document.title).toBe("More, Bar Tab");
  });

  it("redirects #/ to the launch project's Live", async () => {
    const { router } = await mount("#/", { launchProject: "builder" });
    expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/p/builder/live");
  });

  it("shows the project picker at #/ when there is no launch project", async () => {
    await mount("#/");
    const heading = await screen.findByRole("heading", { level: 1, name: "Projects" });
    expect(heading).toHaveFocus();
    expect(document.title).toBe("Projects, Bar Tab");
    // The shell stays behind the modal, with its sidebar linking back to the picker.
    expect(screen.getByRole("dialog", { name: "Projects" })).toContainElement(heading);
    expect(document.querySelector(".shell")).not.toBeNull();
    expect(document.querySelector(".shell-main h1")).toBeNull();
  });

  it("falls back to the picker for an unknown route", async () => {
    await mount("#/nope/never");
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  });

  it("moves focus, title and status on navigation", async () => {
    const { router } = await mount("#/p/builder/live");
    await screen.findByRole("heading", { level: 1, name: "Live" });
    await router.navigate("/p/builder/review/models");
    const heading = await screen.findByRole("heading", { level: 1, name: "Models" });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("Models");
    await waitFor(() => {
      expect(document.title).toBe("Models, Builder, Bar Tab");
    });
  });

  it("keeps the route in the access client", async () => {
    const { access } = await mount("#/p/builder/review/summary?range=30d");
    await screen.findByRole("heading", { level: 1, name: "Summary" });
    expect(access.getRoute()).toBe("/p/builder/review/summary?range=30d");
  });
});
