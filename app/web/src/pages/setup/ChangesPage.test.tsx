/*
 * The Changes page (M6a task a11): day groups with the four columns, the Undo flow with its
 * confirm for a changed file, the older backups, the backup folder line, the empty state and the
 * edits-off note. Over the fake edit server, through the real route tree.
 */
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { editServer, EDIT_KEY, historyRow } from "@/test/edit-server";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
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

const CHANGES = "#/p/builder/setup/changes";

type Over = Parameters<typeof editServer>[1];

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

function open(over: Over = {}, width = 1440) {
  const server = editServer({}, over);
  return { server, mounted: mount(CHANGES, { server, width, editKeys: { builder: EDIT_KEY } }) };
}

const today = historyRow({ id: "row-1", time: "2026-11-11T14:55:00Z" });
const yesterday = historyRow({
  id: "row-2",
  time: "2026-11-10T15:00:00Z",
  field: "maxEffortLevel",
  from: "high",
  to: "xhigh",
  scope: "project",
  display_path: ".claude/settings.json",
  real_path: ".claude/settings.json",
  undo_state: "undone",
  undone_at: "2026-11-10T10:00:00Z",
  recheck: null,
});

describe("rows", () => {
  it("groups by day with the page's breadcrumb, a card for each day and the help on the first", async () => {
    const { mounted } = open({ rows: [today, yesterday] });
    await mounted;
    expect(await screen.findByRole("heading", { level: 1, name: "Changes" })).toHaveFocus();
    const crumbs = screen.getByRole("navigation", { name: en.bc_label });
    expect(within(crumbs).getByRole("link", { name: "Your setup" })).toHaveAttribute(
      "href",
      "#/p/builder/setup",
    );
    await screen.findByText("Effort, xhigh to low");
    const titles = screen
      .getAllByRole("region")
      .map((card) => card.querySelector("h2")?.textContent);
    expect(titles).toEqual(["Today", "Yesterday"]);
    // The history help sits on the first card only.
    const [first, second] = screen.getAllByRole("region");
    expect(within(need(first)).getAllByRole("button", { name: /^About / })).toHaveLength(1);
    expect(within(need(second)).queryByRole("button", { name: /^About / })).toBeNull();
  });

  it("names each change, file and undo state in its own cell, with a screen-reader label", async () => {
    const { mounted } = open({ rows: [today, yesterday] });
    await mounted;
    await screen.findByText("Effort, xhigh to low");
    const rows = screen.getAllByRole("listitem");
    const first = rows.find((row) => row.textContent?.includes("xhigh to low"));
    expect(first).toBeDefined();
    if (first === undefined) return;
    expect(first).toHaveTextContent("Effort, xhigh to low");
    expect(first).toHaveTextContent("Project local");
    expect(first).toHaveTextContent(".claude/settings.local.json");
    // A row that can simply be undone has the button and no "Can undo" label of its own.
    expect(within(first).getByRole("button", { name: en.ed_undo })).toBeInTheDocument();
    expect(first.querySelector(".changes-state")).toBeNull();
    // The column words are visually hidden (sr-only), never display:none, so a screen reader reads them.
    const labels = [...first.querySelectorAll(".changes-cell > .sr-only")].map(
      (el) => el.textContent,
    );
    expect(labels).toEqual([en.cg_col_when, en.cg_col_change, en.cg_col_file, en.cg_col_undo]);
    const second = rows.find((row) => row.textContent?.includes("Effort cap"));
    expect(second).toHaveTextContent(/Undone at /);
    expect(within(need(second)).queryByRole("button", { name: en.ed_undo })).toBeNull();
  });

  it("says a symlinked file links to the real one", async () => {
    const linked = historyRow({ id: "row-3", real_path: "/dotfiles/settings.local.json" });
    const { mounted } = open({ rows: [linked] });
    await mounted;
    expect(await screen.findByText("/dotfiles/settings.local.json")).toBeInTheDocument();
    expect(screen.getByText(en.ed_links_to, { exact: false })).toBeInTheDocument();
  });

  it("words each reason a save can't be undone", async () => {
    const reasons = [
      ["not_newest", en.cg_nu_not_newest],
      ["undo_row", en.cg_nu_undo_row],
      ["backup_pruned", en.cg_nu_backup_pruned],
      ["backup_damaged", en.cg_nu_backup_damaged],
      ["restore_row", en.cg_not_undoable],
      ["file_refused", en.cg_not_undoable],
    ] as const;
    const rows = reasons.map(([reason], index) =>
      historyRow({
        id: `row-n${String(index)}`,
        undo_state: "not_undoable",
        not_undoable_reason: reason,
      }),
    );
    const { mounted } = open({ rows });
    await mounted;
    await screen.findByRole("heading", { level: 1, name: "Changes" });
    for (const [, text] of reasons) {
      expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
    }
    expect(screen.queryByRole("button", { name: en.ed_undo })).toBeNull();
  });
});

describe("Undo", () => {
  it("sends the undo and shows the row as undone", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open({ rows: [today] });
    await mounted;
    await user.click(await screen.findByRole("button", { name: en.ed_undo }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/undo")).toHaveLength(1);
    });
    expect(server.edit.of("/api/edit/undo")[0]?.body).toMatchObject({ row_id: "row-1" });
    expect(await screen.findByText(/Undone at /)).toBeInTheDocument();
  });

  it("opens the undo confirm inline under its row, with focus on it, when the file changed", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open({
      rows: [today],
      undoReply: {
        status: 409,
        body: {
          code: "changed_since_save",
          params: {},
          server_time: "2026-11-11T15:00:00Z",
          undo_preview: {
            version: "u-1",
            diff: {
              new_file: false,
              lines: [{ kind: "del", old_n: 2, new_n: null, text: '  "other": true' }],
            },
          },
        },
      },
    });
    await mounted;
    await user.click(await screen.findByRole("button", { name: en.ed_undo }));
    const heading = await screen.findByRole("heading", { name: en.ed_undo_h });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(heading.closest("li")).not.toBeNull();
    // The panel lists the line the other program added, as a removed line, and folds the lines
    // above it into a counted row instead of cutting them silently.
    const panel = need(heading.closest(".undo-confirm"));
    const removed = [...panel.querySelectorAll(".diff-del")].map((li) => li.textContent);
    expect(removed).toHaveLength(1);
    expect(removed[0]).toContain('"other": true');
    expect(panel.querySelector(".diff-fold")).toHaveTextContent("1 unchanged line");
    await user.click(screen.getByRole("button", { name: en.ed_undo_keep }));
    expect(screen.queryByRole("heading", { name: en.ed_undo_h })).toBeNull();
    // Undo anyway sends the version the preview named.
    server.edit.undoReply = {
      status: 409,
      body: {
        code: "changed_since_save",
        params: {},
        server_time: "2026-11-11T15:00:00Z",
        undo_preview: { version: "u-2", diff: { new_file: false, lines: [] } },
      },
    };
    await user.click(screen.getByRole("button", { name: en.ed_undo }));
    await user.click(await screen.findByRole("button", { name: en.ed_undo_anyway }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/undo").at(-1)?.body).toMatchObject({
        anyway: true,
        version: "u-2",
      });
    });
  });

  it("asks before an undo that deletes the file, and sends it only on Undo anyway", async () => {
    const user = userEvent.setup();
    const made = historyRow({
      id: "row-new",
      op: "create",
      from: null,
      to: "high",
      undo_state: "deletes_file",
    });
    const { server, mounted } = open({ rows: [made] });
    await mounted;
    expect(await screen.findByText("Effort, set to high in a new file")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: en.ed_undo }));
    // The same inline panel as the other undos, with focus on it, and nothing sent yet.
    const heading = await screen.findByRole("heading", { name: en.ed_undo_h });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(heading.closest("li")).not.toBeNull();
    expect(screen.getAllByText(en.cg_deletes_file).length).toBeGreaterThan(0);
    // The panel and its row name the whole path of the file that goes, the project's path in
    // front of the relative one the server sends.
    const whole = "/work/builder/.claude/settings.local.json";
    expect(need(document.querySelector(".undo-confirm-path")).textContent).toBe(whole);
    expect(need(document.querySelector(".changes-file .path-text")).textContent).toBe(whole);
    expect(server.edit.of("/api/edit/undo")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: en.ed_undo_keep }));
    expect(screen.queryByRole("heading", { name: en.ed_undo_h })).toBeNull();
    await user.click(screen.getByRole("button", { name: en.ed_undo }));
    await user.click(await screen.findByRole("button", { name: en.ed_undo_anyway }));
    await waitFor(() => {
      expect(server.edit.of("/api/edit/undo")).toHaveLength(1);
    });
    expect(server.edit.of("/api/edit/undo")[0]?.body).toMatchObject({ row_id: "row-new" });
  });

  it("names the real file under a link in the delete confirm and its row, with ~ for home", async () => {
    const user = userEvent.setup();
    const made = historyRow({
      id: "row-link",
      op: "create",
      from: null,
      to: "high",
      scope: "user",
      display_path: "~/.claude/settings.json",
      real_path: "~/dotfiles/claude/settings.json",
      undo_state: "deletes_file",
    });
    const { mounted } = open({ rows: [made] });
    await mounted;
    await user.click(await screen.findByRole("button", { name: en.ed_undo }));
    await screen.findByRole("heading", { name: en.ed_undo_h });
    const panel = need(document.querySelector(".undo-confirm-path"));
    expect(need(panel.querySelector(".path-text")).textContent).toBe("~/.claude/settings.json");
    expect(need(panel.querySelector(".undo-confirm-real")).textContent).toBe(
      "~/dotfiles/claude/settings.json",
    );
    const row = need(document.querySelector(".changes-file"));
    expect(need(row.querySelector(".changes-real")).textContent).toBe(
      "~/dotfiles/claude/settings.json",
    );
  });

  it("leaves the Undo cell of an undo row empty and reads it as Undid", async () => {
    const undid = historyRow({
      id: "row-u",
      op: "undo",
      undo_state: "not_undoable",
      not_undoable_reason: "undo_row",
      recheck: { state: "confirmed", changed_keys: [], ours_survived: null, seen: false },
    });
    const { mounted } = open({ rows: [undid] });
    await mounted;
    expect(await screen.findByText("Undid Effort, xhigh to low")).toBeInTheDocument();
    const cell = need(document.querySelector(".changes-undo"));
    expect(cell.textContent).toBe(en.cg_col_undo);
    expect(cell.querySelector("button")).toBeNull();
  });

  it("puts the overwritten word and its sentence on separate lines, and shows the confirmed word", async () => {
    const over = historyRow({
      id: "row-o",
      recheck: {
        state: "overwritten",
        changed_keys: ["permissions"],
        ours_survived: true,
        seen: false,
      },
    });
    const ok = historyRow({
      id: "row-ok",
      time: "2026-11-11T14:50:00Z",
      recheck: { state: "confirmed", changed_keys: [], ours_survived: null, seen: false },
    });
    const { mounted } = open({ rows: [over, ok] });
    await mounted;
    const word = await screen.findByText(en.cg_rc_overwritten, { exact: false });
    expect(word.className).toContain("changes-recheck-word");
    expect(word.textContent).not.toContain("still in the file");
    const note = need(word.parentElement?.querySelector(".changes-recheck-note"));
    expect(note).toHaveTextContent("Your effort change is still in the file.");
    const words = [...document.querySelectorAll(".changes-recheck-word")].map(
      (el) => el.textContent,
    );
    expect(words).toContain(`✓ ${en.cg_rc_confirmed}`);
  });

  it("says why an undo was refused, under its row", async () => {
    const user = userEvent.setup();
    const { mounted } = open({
      rows: [today],
      undoReply: {
        status: 409,
        body: { code: "backup_damaged", params: { file: "settings.local.json" } },
      },
    });
    await mounted;
    await user.click(await screen.findByRole("button", { name: en.ed_undo }));
    expect(await screen.findByText(en.er_lead_undo)).toBeInTheDocument();
  });
});

describe("older backups and the backup folder", () => {
  it("keeps older saves in a disclosure and names the real folder with Copy path", async () => {
    const user = userEvent.setup();
    const old = historyRow({ id: "row-old", time: "2026-09-01T09:00:00Z", to: "medium" });
    const { mounted } = open({ rows: [today], older: [old] });
    await mounted;
    const trigger = await screen.findByRole("button", { name: /Older backups/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Effort, xhigh to medium")).toBeInTheDocument();
    expect(screen.getByText("~/backups")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: en.in_copy }));
    expect(await navigator.clipboard.readText()).toBe("/home/me/.config/backups");
  });
});

describe("empty", () => {
  it("says what will appear and links to Your setup", async () => {
    const { mounted } = open();
    await mounted;
    expect(await screen.findByText(en.cg_empty_h)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en.cg_empty_link })).toHaveAttribute(
      "href",
      "#/p/builder/setup",
    );
  });
});

describe("editing off", () => {
  it("shows the history note once at the top, with each Undo aria-disabled", async () => {
    const user = userEvent.setup();
    const { server, mounted } = open({ rows: [today, yesterday], mode: "off" });
    await mounted;
    const note = (await screen.findAllByText(/Undo needs editing on/)).at(0);
    expect(note).toBeDefined();
    expect(screen.getAllByText(/Undo needs editing on/)).toHaveLength(1);
    expect(note).toHaveTextContent("/bartab-preview --allow-edits");
    const undo = await screen.findByRole("button", { name: en.ed_undo });
    expect(undo).toHaveAttribute("aria-disabled", "true");
    await user.click(undo);
    expect(server.edit.of("/api/edit/undo")).toHaveLength(0);
  });
});
