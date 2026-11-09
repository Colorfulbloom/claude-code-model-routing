import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { fakeServer } from "@/test/server";

afterEach(() => {
  cleanup();
  resetViewport();
});

describe("project picker modal (#/ with no launch project)", () => {
  it.each([1440, 375])("is a dialog named Projects whose h1 has focus at %i px", async (width) => {
    await mount("#/", { width });
    const dialog = await screen.findByRole("dialog", { name: "Projects" });
    const heading = within(dialog).getByRole("heading", { level: 1, name: "Projects" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(dialog.closest(".pk-sheet") !== null).toBe(width === 1440);
    expect(dialog.closest(".pk-tray") !== null).toBe(width === 375);
    expect(within(dialog).queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("stays open on Esc when there is nowhere to go back to", async () => {
    const user = userEvent.setup();
    const { router } = await mount("#/");
    await screen.findByRole("dialog", { name: "Projects" });
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Projects" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("goes back on Esc after arriving from another route", async () => {
    const user = userEvent.setup();
    const { router } = await mount("#/reference/glossary");
    await screen.findByRole("heading", { level: 1, name: "Glossary" });
    await act(() => router.navigate("/"));
    const dialog = await screen.findByRole("dialog", { name: "Projects" });
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    // Esc is heard from inside the dialog, so wait for the route harness to focus its h1.
    await waitFor(() => {
      expect(within(dialog).getByRole("heading", { level: 1, name: "Projects" })).toHaveFocus();
    });
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/reference/glossary");
    });
    // The router store changes before React commits the route (RouterProvider renders the new
    // state in a transition), so the dialog leaves the DOM a little after the pathname changes.
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(screen.getByRole("heading", { level: 1, name: "Glossary" })).toBeInTheDocument();
  });

  it.each([1440, 375])("lists every project with its state at %i px", async (width) => {
    await mount("#/", { width });
    const list = await screen.findByRole("listbox", { name: "Projects" });
    const options = within(list).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      expect.stringContaining("Agent working"),
      expect.stringContaining("Ready"),
      expect.stringContaining("No .claude folder"),
      expect.stringContaining("Folder not found"),
    ]);
  });

  it("opens the picked project's Live", async () => {
    const user = userEvent.setup();
    const { router, access } = await mount("#/");
    await user.click(await screen.findByRole("option", { name: /Harbor notes/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/harbor/live");
    });
    expect(access.getProject()).toBe("harbor");
  });

  it("shows the empty state with a heading and a sentence and no command row", async () => {
    await mount("#/", { server: fakeServer({ projects: [] }) });
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(
      screen.getByText("A project appears here after you use Claude Code in it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy command" })).toBeNull();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
