/*
 * The version gap on Your setup (the notice from notices[]) and on the inspector's Why line (the
 * link to the rule and the older-version mark). Both read the rules through useRules, so the tests
 * serve the real rules.json beside the setup answers.
 */
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { en } from "@/strings/en";
import { t, tn } from "@/strings/t";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { rulesServer, type RulesOptions } from "@/test/rules-server";
import { partAnswer, partRow, setupItem, setupMap } from "@/test/setup-fixtures";
import { setupServer } from "@/test/setup-server";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

type Server = ReturnType<typeof setupServer>;

/** A setup server that also answers /api/rules from the real file. */
function withRules(server: Server, options: RulesOptions = {}) {
  const rules = rulesServer(options);
  const base = server.fetch;
  server.fetch = (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return path.startsWith("/api/rules") ? rules.fetch(input, init) : base(input, init);
  };
  return Object.assign(server, { rules });
}

const gap = (due: number) => ({
  code: "version_gap",
  params: { installed: "2.1.310", checked_on: "2.1.302", due: String(due) },
});

const someDue: RulesOptions = {
  installed: "2.1.310",
  mutate: (rules) => {
    for (const rule of rules.slice(0, 4)) {
      rule.verified_on = { ...rule.verified_on, claude_version: "2.1.310" };
      rule.due = false;
    }
  },
};

describe("the notice on Your setup", () => {
  const open = (server: Server) => mount("#/p/builder/setup", { server });

  it("says all the rules were checked on one version, and links the due view", async () => {
    await open(
      withRules(
        setupServer({ map: () => setupMap([partRow("settings")], { notices: [gap(84)] }) }),
        {
          installed: "2.1.310",
        },
      ),
    );
    const text = t("su_n_version_gap", { installed: "2.1.310", checked_on: "2.1.302" });
    const notice = (await screen.findByText(text)).closest("p");
    expect(notice).toHaveTextContent(en.status_unknown);
    expect(within(notice as HTMLElement).getByText(en.status_unknown)).toHaveClass(
      "status-chip",
      "status-chip-unknown",
    );
    const link = within(notice as HTMLElement).getByRole("link", {
      name: t("dc_gap_link_other", { n: 84 }),
    });
    expect(link).toHaveAttribute("href", "#/reference/decides?due=1");
  });

  it("says how many are due when only some are, with the count the page will show", async () => {
    await open(
      withRules(
        // The server's count can include agent field versions, so the page uses the rules' own.
        setupServer({ map: () => setupMap([partRow("settings")], { notices: [gap(83)] }) }),
        someDue,
      ),
    );
    const text = tn("su_n_version_gap_some", 80, { installed: "2.1.310", due: 80 });
    const notice = (await screen.findByText(text)).closest("p");
    expect(
      within(notice as HTMLElement).getByRole("link", { name: "Show the 80 rules to re-check" }),
    ).toHaveAttribute("href", "#/reference/decides?due=1");
  });

  it("shows nothing when the map has no version_gap notice", async () => {
    await open(
      withRules(setupServer({ map: () => setupMap([partRow("settings")]) }), {
        installed: "2.1.310",
      }),
    );
    await screen.findByRole("table", { name: en.su_card_h });
    expect(screen.queryByText(/You run Claude Code/)).toBeNull();
  });

  it("keeps the unlisted notice as it is, and shows each notice once", async () => {
    await open(
      withRules(
        setupServer({
          map: () => setupMap([partRow("settings")], { listed: false, notices: [gap(84)] }),
        }),
        { installed: "2.1.310" },
      ),
    );
    expect(await screen.findByText(/isn't on Bar Tab's project list/)).toBeVisible();
    expect(screen.getAllByText(/isn't on Bar Tab's project list/)).toHaveLength(1);
    expect(screen.getAllByText(/You run Claude Code 2\.1\.310/)).toHaveLength(1);
  });

  it("waits for the rules, so its words never change after it appears", async () => {
    const server = withRules(
      setupServer({ map: () => setupMap([partRow("settings")], { notices: [gap(84)] }) }),
      {
        installed: "2.1.310",
      },
    );
    let release: () => void = () => undefined;
    const held = new Promise<void>((done) => {
      release = done;
    });
    const base = server.rules.fetch;
    server.rules.fetch = async (input, init) => {
      await held;
      return base(input, init);
    };
    await open(server);
    await screen.findByRole("table", { name: en.su_card_h });
    expect(screen.queryByText(/You run Claude Code/)).toBeNull();
    release();
    expect(await screen.findByText(/You run Claude Code 2\.1\.310/)).toBeVisible();
  });

  it("opens How Claude Code decides with only the due rules when its link is followed", async () => {
    const user = userEvent.setup();
    await open(
      withRules(
        setupServer({ map: () => setupMap([partRow("settings")], { notices: [gap(84)] }) }),
        {
          installed: "2.1.310",
        },
      ),
    );
    await user.click(await screen.findByRole("link", { name: t("dc_gap_link_other", { n: 84 }) }));
    await waitFor(() => {
      expect(window.location.hash).toBe("#/reference/decides?due=1");
    });
    expect(await screen.findByText(/Showing all 84 rules/)).toBeVisible();
  });
});

describe("the Why line", () => {
  const item = (over = {}) =>
    setupItem("settings", "effortLevel", {
      status: "lowered",
      reason: { code: "lowered", params: {}, rule_id: "effort-lowered-by-cap", ref_item: null },
      confidence: { level: "tested", tested_on: "2.1.302" },
      ...over,
    });

  async function why(options: RulesOptions, over = {}) {
    const server = withRules(setupServer({ part: (p) => partAnswer(p, [item(over)]) }), options);
    await mount("#/p/builder/setup/settings/effortLevel", { server });
    const region = await screen.findByRole("region", { name: /Effort/ });
    return within(
      await waitFor(() => {
        const found = region.querySelector<HTMLElement>(".inspector-why");
        if (found === null) throw new Error("no Why block");
        return found;
      }),
    );
  }

  it("links the rule behind the reason, by its setting's route", async () => {
    const block = await why({});
    const link = await block.findByRole("link", { name: /^See the rule effort-lowered-by-cap/ });
    expect(link).toHaveAttribute("href", "#/reference/decides/effortLevel/effort-lowered-by-cap");
    expect(link.querySelector("code")).toHaveTextContent("effort-lowered-by-cap");
    expect(block.queryByText(/Older than your/)).toBeNull();
  });

  it("adds the older-version mark beside the confidence line when the rule is due", async () => {
    const block = await why({ installed: "2.1.310" });
    const mark = await block.findByText(t("in_older", { installed: "2.1.310" }));
    expect(mark.closest("p")).toHaveTextContent("tested on 2.1.302");
    expect(mark.closest("p")).toHaveTextContent("▲");
  });

  it("shows no mark and no link for a reason with no rule, or a rule the file lacks", async () => {
    const none = await why(
      { installed: "2.1.310" },
      { reason: { code: "lowered", params: {}, rule_id: null, ref_item: null } },
    );
    expect(none.queryByRole("link")).toBeNull();
    expect(none.queryByText(/Older than your/)).toBeNull();
    cleanup();
    const gone = await why(
      { installed: "2.1.310" },
      { reason: { code: "lowered", params: {}, rule_id: "no-such-rule", ref_item: null } },
    );
    expect(gone.queryByRole("link")).toBeNull();
  });
});
