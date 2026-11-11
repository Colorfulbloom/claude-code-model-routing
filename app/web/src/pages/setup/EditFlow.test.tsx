/*
 * The settings edit flow through the real route tree over a fake edit server (M6a task a11): Edit
 * in the inspector, the rail, Save with its refusals and restart, the Saved box with its recheck
 * line, the Overwritten warning, and the edits-off states. The Changes page has its own test file.
 */
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { editServer, EDIT_KEY, historyRow } from "@/test/edit-server";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { partAnswer, setupItem, source } from "@/test/setup-fixtures";
import { en } from "@/strings/en";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

const effort = setupItem("settings", "effortLevel", {
  status: "in_effect",
  effective: { value: { text: "xhigh", masked: false }, origin: "set", by_item: null },
  sources: [
    source({
      scope: "project_local",
      key: "effortLevel",
      file: ".claude/settings.local.json",
      full_path: "/work/builder/.claude/settings.local.json",
      line: 3,
      value: { text: "xhigh", masked: false },
      status: "in_effect",
    }),
  ],
});
const thinking = setupItem("settings", "alwaysThinkingEnabled", {
  effective: { value: { text: "true", masked: false }, origin: "set", by_item: null },
  sources: [source({ key: "alwaysThinkingEnabled", value: { text: "true", masked: false } })],
});

const ITEM = "#/p/builder/setup/settings/effortLevel";
const EDIT_ROUTE = `${ITEM}/edit`;
const KEYS = { builder: EDIT_KEY };

type Over = Parameters<typeof editServer>[1];

function open(hash: string, over: Over = {}, width = 1440, keys: Record<string, string> = KEYS) {
  const server = editServer({ part: (part) => partAnswer(part, [effort, thinking]) }, over);
  return { server, mounted: mount(hash, { server, width, editKeys: keys }) };
}

const edit = (name = "Edit effort") => screen.findByRole("button", { name });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

describe("Edit in the inspector", () => {
  it("opens the rail beside the list, focuses its heading and previews the starting value", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(ITEM);
    await mounted;
    const link = await screen.findByRole("link", { name: "Edit effort" });
    expect(link).toHaveAttribute("href", "#/p/builder/setup/settings/effortLevel/edit");
    await user.click(link);
    const heading = await screen.findByRole("heading", { level: 2, name: "Edit effort" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    // The list stays beside the rail on desktop.
    expect(screen.getByRole("navigation", { name: "Settings" })).toBeInTheDocument();
    await screen.findByRole("heading", { level: 3, name: en.ed_this_save_h });
    const first = server.edit.of("/api/edit/preview")[0];
    expect(first?.body).toMatchObject({
      op: "set",
      scope: "local",
      field: "effortLevel",
      value: "xhigh",
    });
    // The same value as the file holds. That is no error: This save says so in one neutral line, with
    // no Set to rows and no diff box, and Save is aria-disabled, focusable and described by the line.
    const neutral = await screen.findByText(en.ed_pick_other);
    expect(screen.queryByText(en.er_no_change, { exact: false })).toBeNull();
    const card = need(neutral.closest<HTMLElement>(".this-save"));
    expect(card.querySelector(".diff")).toBeNull();
    expect(within(card).queryByText(en.ed_l_set)).toBeNull();
    const save = await screen.findByRole("button", { name: /^Save to / });
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(save).toHaveAttribute("aria-describedby", neutral.id);
    expect(save).toHaveClass("button-primary");
    save.focus();
    expect(save).toHaveFocus();
    expect(server.edit.of("/api/edit/save")).toHaveLength(0);
  });

  it("shows each effort option with what it would run at", async () => {
    const user = userEvent.setup();
    const { mounted } = open(EDIT_ROUTE);
    await mounted;
    const group = await screen.findByRole("radiogroup", { name: "Effort" });
    for (const level of ["low", "medium", "high", "xhigh"]) {
      expect(
        within(group).getByRole("radio", { name: new RegExp(`^${level}`) }),
      ).toBeInTheDocument();
    }
    await user.click(within(group).getByRole("radio", { name: /^low/ }));
    expect(within(group).getByRole("radio", { name: /^low/ })).toBeChecked();
  });

  it("saves the picked value, closes the rail on the inspector and shows the Saved box", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(EDIT_ROUTE);
    await mounted;
    await user.click(await screen.findByRole("radio", { name: /^low/ }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/preview").at(-1)?.body?.value).toBe("low");
    });
    await user.click(await screen.findByRole("button", { name: /^Save to / }));
    const save = server.edit.of("/api/edit/save")[0];
    expect(save?.body).toMatchObject({ scope: "local", field: "effortLevel", value: "low" });
    expect(await screen.findByText(en.ed_saved)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Edit effort" })).toBeNull();
    expect(window.location.hash).toBe(ITEM);
    const region = await screen.findByRole("region", { name: "Effort" });
    expect(within(region).getByRole("link", { name: en.ed_all_changes })).toHaveAttribute(
      "href",
      "#/p/builder/setup/changes",
    );
    expect(within(region).getByRole("button", { name: en.ed_undo })).toBeInTheDocument();
    // The recheck line settles once, at about two seconds.
    expect(
      await within(region).findByText(
        /Checked the file\. It still holds low\./,
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
  });

  it("holds Save while the preview is pending", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(EDIT_ROUTE);
    await mounted;
    await screen.findByRole("heading", { level: 3, name: en.ed_this_save_h });
    await user.click(screen.getByRole("radio", { name: /^medium/ }));
    // Pressed at once, before the new preview has rendered, so the save waits for it.
    await user.click(screen.getByRole("button", { name: /^Save to / }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/save")).toHaveLength(1);
    });
    expect(server.edit.of("/api/edit/save")[0]?.body?.value).toBe("medium");
  });

  it("moves focus to the refusal, which has no alert role, and keeps the rail open", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(EDIT_ROUTE, {
      saveReply: { status: 409, code: "changed", params: { file: "settings.local.json" } },
    });
    await mounted;
    await user.click(await screen.findByRole("radio", { name: /^low/ }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/preview").at(-1)?.body?.value).toBe("low");
    });
    await user.click(await screen.findByRole("button", { name: /^Save to / }));
    const lead = await screen.findByText(en.er_lead);
    const message = lead.closest(".refused");
    expect(message).not.toBeNull();
    await waitFor(() => {
      expect(message).toHaveFocus();
    });
    expect(message).not.toHaveAttribute("role", "alert");
    expect(screen.getByRole("heading", { level: 2, name: "Edit effort" })).toBeInTheDocument();
  });

  it("shows the restart box, with no alert role, when the server no longer knows the edit key", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(EDIT_ROUTE, {
      saveReply: { status: 403, code: "edit_key_unknown" },
    });
    await mounted;
    await user.click(await screen.findByRole("radio", { name: /^low/ }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/preview").at(-1)?.body?.value).toBe("low");
    });
    await user.click(await screen.findByRole("button", { name: /^Save to / }));
    const head = await screen.findByText(en.eo_restart_on_h);
    const box = head.closest(".restart-box");
    await waitFor(() => {
      expect(box).toHaveFocus();
    });
    expect(box).not.toHaveAttribute("role", "alert");
    expect(screen.getByRole("button", { name: en.eo_reload })).toBeInTheDocument();
    // The whole rail is inert. Save is aria-disabled and described by the box, the control and the
    // Save to rows are locked, and another press sends nothing.
    const save = screen.getByRole("button", { name: /^Save to / });
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(save).toHaveAttribute("aria-describedby", box?.id ?? "");
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
    await user.click(save);
    expect(server.edit.of("/api/edit/save")).toHaveLength(1);
  });

  it("treats a page with no edit key as a restart before anything is sent", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(EDIT_ROUTE, {}, 1440, {});
    await mounted;
    await user.click(await screen.findByRole("radio", { name: /^low/ }));
    expect(await screen.findByText(en.eo_restart_on_h)).toBeInTheDocument();
    expect(server.edit.of("/api/edit/save")).toHaveLength(0);
  });

  it("goes back to the inspector on Cancel, with focus on its heading", async () => {
    const user = userEvent.setup();
    const { mounted } = open(EDIT_ROUTE);
    await mounted;
    await user.click(await screen.findByRole("button", { name: en.ed_cancel }));
    const heading = await screen.findByRole("heading", { level: 2, name: "Effort" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(window.location.hash).toBe(ITEM);
  });

  it("opens a full-height sheet over the item page at 375", async () => {
    const { mounted } = open(EDIT_ROUTE, {}, 375);
    await mounted;
    const sheet = await screen.findByRole("dialog", { name: "Edit effort" });
    expect(within(sheet).getByRole("button", { name: /^Save to / })).toBeInTheDocument();
  });
});

describe("an item with no editor yet", () => {
  it("says so with Copy path and offers no Edit", async () => {
    const { mounted } = open("#/p/builder/setup/settings/alwaysThinkingEnabled");
    await mounted;
    const region = await screen.findByRole("region", { name: /Thinking/ });
    expect(within(region).queryByRole("link", { name: /^Edit/ })).toBeNull();
    expect(within(region).queryByRole("button", { name: /^Edit/ })).toBeNull();
    expect(within(region).getByRole("button", { name: "Copy path" })).toBeInTheDocument();
  });

  it("sends an edit URL for it back to the item", async () => {
    const { mounted } = open("#/p/builder/setup/settings/alwaysThinkingEnabled/edit");
    await mounted;
    await screen.findByRole("region", { name: /Thinking/ });
    await waitFor(() => {
      expect(window.location.hash).toBe("#/p/builder/setup/settings/alwaysThinkingEnabled");
    });
  });
});

describe("editing off", () => {
  it("keeps Edit in the foot, aria-disabled and tied to one reason line", async () => {
    const { mounted } = open(ITEM, { mode: "off" });
    await mounted;
    const button = await edit();
    expect(button).toHaveAttribute("aria-disabled", "true");
    const reason = screen.getByText(/Editing is off\. Start Bar Tab with/);
    const id = reason.getAttribute("id");
    expect(id).not.toBeNull();
    expect(button.getAttribute("aria-describedby")?.split(" ")).toContain(id);
    expect(reason).toHaveTextContent("/bartab-preview --allow-edits");
    button.focus();
    expect(button).toHaveFocus();
  });

  it("renders the item page with a focused route note on an edit URL", async () => {
    const { mounted } = open(EDIT_ROUTE, { mode: "off" });
    await mounted;
    await screen.findByRole("region", { name: "Effort" });
    expect(screen.queryByRole("heading", { level: 2, name: "Edit effort" })).toBeNull();
    const note = await screen.findByText(/opened without its editor/);
    const frame = note.closest("[tabindex='-1']");
    expect(frame).not.toBeNull();
    await waitFor(() => {
      expect(frame).toHaveFocus();
    });
    expect(frame).toHaveTextContent("/bartab-preview --allow-edits");
  });

  it("shows a demo run's reason in the lock box, with no Edit button at all", async () => {
    const demo = open(ITEM, { mode: "unavailable" });
    await demo.mounted;
    const region = await screen.findByRole("region", { name: "Effort" });
    const box = need(region.querySelector<HTMLElement>(".inspector-readonly"));
    expect(box).toHaveTextContent(en.ro_h);
    expect(box).toHaveTextContent(en.eo_reason_demo);
    expect(screen.queryByRole("button", { name: "Edit effort" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Edit effort" })).toBeNull();
  });
});

describe("the Overwritten warning", () => {
  const overwritten = historyRow({
    id: "row-9",
    recheck: {
      state: "overwritten",
      changed_keys: ["effortLevel"],
      ours_survived: false,
      seen: false,
    },
  });

  it("returns on a later visit until it is marked seen, and Review changes opens the drift", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open(ITEM, { warning: overwritten, rows: [overwritten] });
    await mounted;
    const review = await screen.findByRole("button", { name: /Review changes/ });
    expect(server.edit.of("/api/edit/rows/row-9/seen")).toHaveLength(0);
    await user.click(review);
    await waitFor(() => {
      expect(server.edit.of("/api/edit/rows/row-9/drift")).toHaveLength(1);
    });
    await waitFor(() => {
      expect(server.edit.of("/api/edit/rows/row-9/seen")).toHaveLength(1);
    });
    // Marking it seen doesn't take the box off the screen on this visit.
    expect(screen.getByRole("button", { name: /Review changes/ })).toBeInTheDocument();
  });
});
