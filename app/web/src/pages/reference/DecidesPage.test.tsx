import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { en, type StringKey } from "@/strings/en";
import { RULE_GROUP_ORDER } from "@/strings/lists";
import { t } from "@/strings/t";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { ruleRows, rulesAnswer, rulesServer, type RulesOptions } from "@/test/rules-server";
import { filterRules, ruleFields, settingName } from "./rules-view";

beforeAll(() => {
  // jsdom has no scrollIntoView.
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(() => {
  cleanup();
  resetViewport();
  postStatus("");
});

/*
 * The announcement waits 600 ms after typing settles. These tests run on real timers, because fake
 * timers stall userEvent, and they wait for the status region with waitFor.
 */
const SETTLE_MS = 1500;

/** The first of a list, or a failure with a name, so a test never leans on a non-null assertion. */
function first<T>(list: readonly T[]): T {
  const [found] = list;
  if (found === undefined) throw new Error("the list is empty");
  return found;
}

const sleep = (ms: number) =>
  act(async () => {
    await new Promise((done) => setTimeout(done, ms));
  });

async function open(path = "", options: RulesOptions = {}, width = 1440) {
  const server = rulesServer(options);
  const view = await mount(`#/reference/decides${path}`, { server, width });
  return { ...view, server };
}

/** The status region the SearchField owns, not the route's one. */
function announcer(): HTMLElement {
  const regions = screen.getAllByRole("status");
  const found = regions.find((region) => region.closest(".search") !== null);
  if (found === undefined) throw new Error("no search status region");
  return found;
}

const hash = () => window.location.hash;
const sentence = (id: string) => en[`rl_${id}` as StringKey];

describe("How Claude Code decides", () => {
  describe("the rest state", () => {
    it("lists the 17 settings in RULE_GROUP_ORDER, named by rg_ words", async () => {
      await open();
      const nav = await screen.findByRole("navigation", { name: en.sf_settings });
      const links = within(nav).getAllByRole("link");
      expect(links).toHaveLength(RULE_GROUP_ORDER.length);
      expect(links.map((link) => link.querySelector("code")?.textContent)).toEqual([
        ...RULE_GROUP_ORDER,
      ]);
      expect(within(nav).getByText(settingName("effortLevel"))).toBeVisible();
      expect(within(nav).getByText("17")).toBeVisible();
    });

    it("shows the first setting's page with its order and its rules under their status", async () => {
      await open();
      const page = await screen.findByRole("region", {
        name: new RegExp(`^${settingName("effortLevel")}`),
      });
      expect(within(page).getByRole("heading", { level: 2 })).toHaveTextContent("Effort level");
      expect(within(page).getByText("effortLevel")).toBeVisible();
      expect(within(page).getByText(/^14 rules\. Applies to the main session\.$/)).toBeVisible();
      // The ladder: env, flag, managed, cli, local, project, user, default.
      const ladder = within(page).getByRole("list", { name: en.dc_order_h });
      expect(
        within(ladder)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual([
        `1${en.ly_env}`,
        `2${en.ly_flag}`,
        `3${en.sc_managed}`,
        `4${en.ly_cli}`,
        `5${en.sc_project_local}`,
        `6${en.sc_project}`,
        `7${en.sc_user}`,
        `8${en.ly_default}`,
      ]);
      // Groups follow the status order, Invalid first. Effort level has no Invalid rule here.
      const headings = within(page)
        .getAllByRole("heading", { level: 3 })
        .map((heading) => heading.textContent ?? "");
      const order = [
        en.dc_q_lowered,
        en.dc_q_ignored,
        en.dc_q_unknown,
        en.dc_q_in_effect,
        en.dc_q_default,
      ];
      const found = order.map((question) => headings.findIndex((h) => h.includes(question)));
      expect(found.every((at) => at >= 0)).toBe(true);
      expect([...found].sort((a, b) => a - b)).toEqual(found);
    });

    it("groups a rule under its outcome and shows its words", async () => {
      await open();
      const row = (await screen.findByText(sentence("effort-lowered-by-cap"))).closest("li");
      expect(row).not.toBeNull();
      const item = within(row as HTMLElement);
      expect(item.getByText("effort-lowered-by-cap")).toBeVisible();
      expect(item.getByText(en.in_tested)).toBeVisible();
      expect(item.getByText(/^Checked on 2\.1\.302, October 29$/)).toBeVisible();
      expect(item.queryByText(en.dc_due_mark)).toBeNull();
      // Under Lowered, with its question and a count.
      const group = (row as HTMLElement).closest(".ref-os");
      expect(group?.getAttribute("data-status")).toBe("lowered");
      expect(within(group as HTMLElement).getByRole("heading", { level: 3 })).toHaveTextContent(
        `${en.status_lowered}${en.dc_q_lowered}3`,
      );
    });

    it("hides each docs line until the Disclosure opens, and links it in a new tab", async () => {
      const user = userEvent.setup();
      await open();
      const row = (await screen.findByText(sentence("effort-lowered-by-cap"))).closest("li");
      const item = within(row as HTMLElement);
      const trigger = item.getByRole("button", { name: en.dc_docs_one });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      await user.click(trigger);
      expect(trigger).toHaveAttribute("aria-expanded", "true");
      const link = item.getByRole("link", { name: new RegExp(en.dc_new_tab) });
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link.getAttribute("href")).toMatch(/^https:\/\/code\.claude\.com\//);
    });

    it("says why a rule with no docs line has none", async () => {
      await open();
      const row = (await screen.findByText(sentence("effort-env-empty-ignored"))).closest("li");
      expect(within(row as HTMLElement).getByText(en.dc_nodocs_tested)).toBeVisible();
      expect(within(row as HTMLElement).queryByRole("button")).toBeNull();
    });

    it("leaves focus on the h1 for a plain load", async () => {
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      await waitFor(() => {
        expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
      });
    });
  });

  describe("a rule under every status it leads to", () => {
    // In effect and Invalid, so the page draws it twice, Invalid first.
    const TWICE = "effort-level-settings-values";

    const rowsOf = async (id: string): Promise<HTMLElement[]> =>
      (await screen.findAllByText(sentence(id))).map((el) => el.closest("li") as HTMLElement);

    it("shows a two-status rule in both of its groups, Invalid first", async () => {
      await open("/effortLevel");
      const rows = await rowsOf(TWICE);
      expect(rows).toHaveLength(2);
      expect(rows.map((row) => row.closest(".ref-os")?.getAttribute("data-status"))).toEqual([
        "invalid",
        "in_effect",
      ]);
    });

    it("counts each group's own rows, and the page still counts the rule once", async () => {
      await open("/effortLevel");
      await rowsOf(TWICE);
      const page = screen.getByRole("region", {
        name: new RegExp(`^${settingName("effortLevel")}`),
      });
      const rules = ruleRows().filter((rule) => rule.key === "effortLevel");
      expect(
        within(page).getByText(`${String(rules.length)} rules. Applies to the main session.`),
      ).toBeVisible();
      let rows = 0;
      for (const group of page.querySelectorAll<HTMLElement>(".ref-os")) {
        const n = group.querySelectorAll("li.ref-rule").length;
        expect(within(group).getByRole("heading", { level: 3 })).toHaveTextContent(
          new RegExp(`${String(n)}$`),
        );
        rows += n;
      }
      const extra = rules.reduce((sum, rule) => sum + rule.outcomes.length - 1, 0);
      expect(extra).toBeGreaterThan(0);
      expect(rows).toBe(rules.length + extra);
    });

    it("focuses the first occurrence from a deep link and gives the other no id", async () => {
      await open(`/effortLevel/${TWICE}`);
      const rows = await rowsOf(TWICE);
      expect(rows).toHaveLength(2);
      const [firstRow, second] = rows as [HTMLElement, HTMLElement];
      expect(firstRow.closest(".ref-os")?.getAttribute("data-status")).toBe("invalid");
      expect(firstRow).toHaveAttribute("aria-current", "true");
      expect(firstRow).toHaveClass("ref-rule-on");
      expect(firstRow).toHaveAttribute("data-rule-id", TWICE);
      await waitFor(() => {
        expect(document.activeElement).toBe(firstRow);
      });
      expect(second).not.toHaveAttribute("aria-current");
      expect(second).not.toHaveClass("ref-rule-on");
      expect(second).not.toHaveAttribute("data-rule-id");
      expect(second).not.toHaveAttribute("tabindex");
    });

    it("keeps every rule id on the page unique", async () => {
      await open("/effortLevel");
      await rowsOf(TWICE);
      const ids = Array.from(document.querySelectorAll("[data-rule-id]")).map((el) =>
        el.getAttribute("data-rule-id"),
      );
      expect(new Set(ids).size).toBe(ids.length);
      expect(ids).toContain(TWICE);
      expect(document.querySelectorAll("li.ref-rule").length).toBeGreaterThan(ids.length);
    });

    it("says once, under the order ladder, that a rule shows under each status", async () => {
      await open("/effortLevel");
      await rowsOf(TWICE);
      const notes = screen.getAllByText(en.dc_results_note);
      expect(notes).toHaveLength(1);
      const order = screen.getByRole("list", { name: en.dc_order_h });
      expect(
        order.compareDocumentPosition(first(notes)) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it("leaves the note out of a setting whose rules each show once", async () => {
      const single = [...new Set(ruleRows().map((rule) => rule.key))].find((key) =>
        ruleRows()
          .filter((rule) => rule.key === key)
          .every((rule) => rule.outcomes.length <= 1),
      );
      if (single === undefined) throw new Error("every setting has a two-status rule");
      await open(`/${single}`);
      await screen.findByRole("region", { name: settingName(single) });
      expect(screen.queryByText(en.dc_results_note)).toBeNull();
    });

    it("counts a searched two-status rule once and shows it once, under its setting", async () => {
      await open(`?q=${TWICE}`);
      const pane = await screen.findByRole("region", { name: t("dc_results_one", { n: 1, g: 1 }) });
      expect(pane.querySelectorAll("li.ref-rule")).toHaveLength(1);
      expect(pane.querySelectorAll(`[data-rule-id="${TWICE}"]`)).toHaveLength(1);
      expect(pane.querySelector(".ref-os-h .status-chip, .ref-os-h [data-status]")).toBeNull();
      expect(screen.getByText("1 of 84 rules", { selector: "p" })).toBeVisible();
      const nav = screen.getByRole("navigation", { name: en.sf_settings });
      expect(within(nav).getByText("1 of 17")).toBeVisible();
      expect(screen.queryByText(en.dc_results_note)).toBeNull();
    });
  });

  describe("routes", () => {
    it("opens a setting from its own route, so Back works", async () => {
      const user = userEvent.setup();
      const { router } = await open();
      const nav = await screen.findByRole("navigation", { name: en.sf_settings });
      await user.click(within(nav).getByRole("link", { name: /Cache lifetime/ }));
      await waitFor(() => {
        expect(hash()).toBe("#/reference/decides/promptCacheTtl");
      });
      const page = await screen.findByRole("region", { name: settingName("promptCacheTtl") });
      expect(within(page).getByRole("heading", { level: 2 })).toHaveFocus();
      expect(within(nav).getByRole("link", { name: /Cache lifetime/ })).toHaveAttribute(
        "aria-current",
        "page",
      );
      await act(async () => {
        await router.navigate(-1);
      });
      await waitFor(() => {
        expect(hash()).toBe("#/reference/decides");
      });
      expect(
        await screen.findByRole("region", { name: new RegExp(settingName("effortLevel")) }),
      ).toBeVisible();
    });

    it("marks a rule reached by route, opens its docs and focuses it", async () => {
      await open("/effortLevel/effort-lowered-by-cap");
      const row = (await screen.findByText(sentence("effort-lowered-by-cap"))).closest("li");
      expect(row).toHaveAttribute("aria-current", "true");
      expect(row).toHaveClass("ref-rule-on");
      await waitFor(() => {
        expect(document.activeElement).toBe(row);
      });
      expect(
        within(row as HTMLElement).getByRole("button", { name: en.dc_docs_one }),
      ).toHaveAttribute("aria-expanded", "true");
    });

    it("keeps its filters on a setting link", async () => {
      const user = userEvent.setup();
      await open("?confidence=documented");
      const nav = await screen.findByRole("navigation", { name: en.sf_settings });
      const link = first(within(nav).getAllByRole("link"));
      expect(link.getAttribute("href")).toMatch(
        /#\/reference\/decides\/[^?]+\?confidence=documented$/,
      );
      await user.click(link);
      await waitFor(() => {
        expect(hash()).toMatch(/\?confidence=documented$/);
      });
    });

    it("sends a path with too many segments to the picker", async () => {
      await open("/a/b/c");
      await waitFor(() => {
        expect(hash()).toBe("#/");
      });
    });
  });

  describe("stale ids and hidden targets", () => {
    it("says a stale setting key is gone and links to the whole list", async () => {
      await open("/noSuchSetting");
      expect(
        await screen.findByRole("heading", {
          name: t("dc_gone_setting_h", { key: "noSuchSetting" }),
        }),
      ).toBeVisible();
      expect(screen.getByText(en.sp_gone_b)).toBeVisible();
      const link = screen.getByRole("link", { name: en.dc_gone_link });
      expect(link).toHaveAttribute("href", "#/reference/decides");
      await waitFor(() => {
        expect(link).toHaveFocus();
      });
    });

    it("says a stale rule id is gone, and so is a rule of another setting", async () => {
      await open("/effortLevel/no-such-rule");
      expect(
        await screen.findByRole("heading", { name: t("dc_gone_rule_h", { id: "no-such-rule" }) }),
      ).toBeVisible();
      cleanup();
      await open("/effortLevel/model-main-default");
      expect(
        await screen.findByRole("heading", {
          name: t("dc_gone_rule_h", { id: "model-main-default" }),
        }),
      ).toBeVisible();
    });

    it("shows a rule the search hides, and keeps its setting in the list", async () => {
      await open("/effortLevel/effort-lowered-by-cap?q=zzzznothing");
      const row = (await screen.findByText(sentence("effort-lowered-by-cap"))).closest("li");
      expect(row).toHaveClass("ref-rule-on");
      const nav = screen.getByRole("navigation", { name: en.sf_settings });
      expect(within(nav).getAllByRole("link")).toHaveLength(1);
      expect(within(nav).getByText(/0 of 14/)).toBeVisible();
    });

    it("shows a rule the Confidence filter hides", async () => {
      await open("/effortLevel/effort-lowered-by-cap?confidence=assumed");
      const row = (await screen.findByText(sentence("effort-lowered-by-cap"))).closest("li");
      expect(row).toHaveClass("ref-rule-on");
      // Its sibling rules that are not Assumed stay out.
      expect(screen.queryByText(sentence("effort-level-layer-order"))).toBeNull();
    });
  });

  describe("search", () => {
    it("shows one results pane across settings, and keeps the query in the URL", async () => {
      const user = userEvent.setup();
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      await user.type(screen.getByRole("searchbox", { name: en.dc_search_label }), "cache");
      const expected = filterRules(ruleRows(), { q: "cache", confidence: "all", due: false });
      const settings = new Set(expected.map((entry) => entry.rule.key));
      const pane = await screen.findByRole("region", {
        name: new RegExp(`^${String(expected.length)} rules in ${String(settings.size)} settings$`),
      });
      expect(pane).toBeVisible();
      expect(hash()).toBe("#/reference/decides?q=cache");
      const nav = screen.getByRole("navigation", { name: en.sf_settings });
      expect(within(nav).getAllByRole("link")).toHaveLength(settings.size);
      expect(within(nav).getByText(`${String(settings.size)} of 17`)).toBeVisible();
      // Matches are marked, by splitting text, never as HTML.
      expect(pane.querySelectorAll("mark").length).toBeGreaterThan(0);
    });

    it("counts in the visible line and says the same thing once typing settles", async () => {
      const user = userEvent.setup();
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      expect(screen.getByText("84 rules", { selector: "p" })).toBeVisible();
      expect(announcer()).toBeEmptyDOMElement();
      await user.type(screen.getByRole("searchbox", { name: en.dc_search_label }), "cache");
      const n = filterRules(ruleRows(), { q: "cache", confidence: "all", due: false }).length;
      expect(screen.getByText(`${String(n)} of 84 rules`, { selector: "p" })).toBeVisible();
      // Nothing yet at once, because the wait restarts on each key.
      expect(announcer()).toBeEmptyDOMElement();
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(`${String(n)} of 84 rules shown`);
        },
        { timeout: SETTLE_MS },
      );
    });

    it("announces after a Confidence change and after Clear", async () => {
      const user = userEvent.setup();
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      await user.click(screen.getByRole("button", { name: new RegExp(en.dc_conf_label) }));
      await user.click(await screen.findByRole("option", { name: new RegExp(en.in_assumed) }));
      const assumed = ruleRows().filter((rule) => rule.confidence === "assumed").length;
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(`${String(assumed)} of 84 rules shown`);
        },
        { timeout: SETTLE_MS },
      );
      expect(hash()).toBe("#/reference/decides?confidence=assumed");
      await user.type(screen.getByRole("searchbox", { name: en.dc_search_label }), "zzzz");
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(en.dc_count_ann_none);
        },
        { timeout: SETTLE_MS },
      );
      // Clear drops the query, and the count goes back to the Confidence-only count.
      await user.click(first(screen.getAllByRole("button", { name: en.sf_clear })));
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(`${String(assumed)} of 84 rules shown`);
        },
        { timeout: SETTLE_MS },
      );
      expect(screen.getByRole("searchbox", { name: en.dc_search_label })).toHaveFocus();
    });

    it("says nothing on load or on a route change", async () => {
      await open("?q=cache");
      await screen.findByRole("region", { name: /rules in \d+ settings$/ });
      await sleep(900);
      expect(announcer()).toBeEmptyDOMElement();
    });

    it("says a row's match was only in the docs, and opens its docs line", async () => {
      const user = userEvent.setup();
      // A word that sits in exactly one rule's docs line and in none of that rule's other fields.
      const rows = ruleRows();
      let pick: { id: string; word: string } | null = null;
      for (const rule of rows) {
        const others = Object.entries(ruleFields(rule))
          .filter(([name]) => name !== "quotes")
          .map(([, text]) => text.toLowerCase())
          .join(" ");
        for (const word of rule.quotes.flatMap(
          (quote) => quote.quote.toLowerCase().match(/[a-z]{8,}/g) ?? [],
        )) {
          const hits = filterRules(rows, { q: word, confidence: "all", due: false });
          if (!others.includes(word) && hits.length === 1 && hits[0]?.docsOnly) {
            pick = { id: rule.rule_id, word };
            break;
          }
        }
        if (pick !== null) break;
      }
      if (pick === null) throw new Error("no docs-only word in rules.json");
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      await user.type(screen.getByRole("searchbox", { name: en.dc_search_label }), pick.word);
      const row = (await screen.findByText(pick.id)).closest("li") as HTMLElement;
      expect(within(row).getByText(en.dc_found_in_docs)).toBeVisible();
      expect(within(row).getByRole("button", { name: /from the docs$/ })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(row.querySelectorAll("mark").length).toBeGreaterThan(0);
    });

    it("does not say found in docs when the rule's own words match too", async () => {
      const user = userEvent.setup();
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      await user.type(screen.getByRole("searchbox", { name: en.dc_search_label }), "effortLevel");
      const row = (await screen.findByText("effort-level-layer-order")).closest(
        "li",
      ) as HTMLElement;
      // The key matches, so the match is not only in the docs line, whatever other rows say.
      expect(within(row).queryByText(en.dc_found_in_docs)).toBeNull();
    });

    it("has a no-results card with the query, Clear search and a Glossary link", async () => {
      const user = userEvent.setup();
      await open("?q=teleportation");
      const card = await screen.findByRole("heading", {
        name: t("dc_none_h", { query: "teleportation" }),
      });
      expect(card).toBeVisible();
      expect(screen.getByRole("link", { name: en.dc_none_glossary })).toHaveAttribute(
        "href",
        "#/reference/glossary?q=teleportation",
      );
      await user.click(
        first(
          within(screen.getByRole("main")).getAllByRole("button", { name: en.sf_clear }).reverse(),
        ),
      );
      await waitFor(() => {
        expect(hash()).toBe("#/reference/decides");
      });
      expect(await screen.findByRole("navigation", { name: en.sf_settings })).toBeVisible();
    });
  });

  describe("loading and failing", () => {
    it("shows bones, a Confidence select with no counts and a count bone, then applies a q in the URL", async () => {
      const server = rulesServer();
      let release: () => void = () => undefined;
      server.rules.answer = () =>
        new Promise((done) => {
          release = () => {
            done(rulesAnswer());
          };
        });
      await mount("#/reference/decides?q=cache", { server });
      expect(
        (await screen.findAllByText(en.dc_loading, { selector: ".sr-only" })).length,
      ).toBeGreaterThan(0);
      const select = screen.getByRole("button", { name: new RegExp(en.dc_conf_label) });
      expect(select).toHaveTextContent(/All$/);
      expect(select.textContent).not.toMatch(/\d/);
      expect(screen.getByRole("searchbox", { name: en.dc_search_label })).toHaveValue("cache");
      expect(screen.queryByText(/rules$/, { selector: "p.search-count" })).toBeNull();
      act(() => {
        release();
      });
      expect(await screen.findByRole("region", { name: /rules in \d+ settings$/ })).toBeVisible();
      expect(screen.getByRole("button", { name: new RegExp(en.dc_conf_label) })).toHaveTextContent(
        /All 84$/,
      );
    });

    it("keeps the same search field, with its focus and text, when the rules arrive", async () => {
      const user = userEvent.setup();
      const server = rulesServer();
      let release: () => void = () => undefined;
      server.rules.answer = () =>
        new Promise((done) => {
          release = () => {
            done(rulesAnswer());
          };
        });
      await mount("#/reference/decides", { server });
      const field = await screen.findByRole("searchbox", { name: en.dc_search_label });
      await user.click(field);
      await user.keyboard("cac");
      act(() => {
        release();
      });
      expect(await screen.findByRole("region", { name: /rules in \d+ settings$/ })).toBeVisible();
      // The same node, not a rebuilt one, so a keystroke after the data lands is not lost.
      expect(screen.getByRole("searchbox", { name: en.dc_search_label })).toBe(field);
      expect(field).toHaveFocus();
      await user.keyboard("he");
      expect(field).toHaveValue("cache");
    });

    it("shows one error with Try again, and asks again", async () => {
      const user = userEvent.setup();
      const server = rulesServer();
      server.rules.answer = () => 500;
      await mount("#/reference/decides", { server });
      expect(await screen.findByRole("heading", { name: en.dc_err_h })).toBeVisible();
      expect(screen.getByRole("alert")).toBeVisible();
      // No count bone waits for a number that will not come.
      expect(document.querySelector(".ref-count-bone")).toBeNull();
      server.rules.answer = () => rulesAnswer();
      await user.click(screen.getByRole("button", { name: en.er_try }));
      expect(await screen.findByRole("navigation", { name: en.sf_settings })).toBeVisible();
    });
  });

  describe("the version gap", () => {
    it("says every rule is due on one version, and links the due view", async () => {
      await open("", { installed: "2.1.310" });
      const notice = (await screen.findByText(/Bar Tab checked all 84 rules on 2\.1\.302/)).closest(
        "p",
      );
      expect(notice).toHaveTextContent("You run Claude Code 2.1.310");
      const link = within(notice as HTMLElement).getByRole("link", {
        name: t("dc_gap_link_other", { n: 84 }),
      });
      expect(link).toHaveAttribute("href", "#/reference/decides?due=1");
    });

    it("says how many rules are due when only some are", async () => {
      await open("", {
        installed: "2.1.310",
        mutate: (rules) => {
          for (const rule of rules.slice(0, 4)) {
            rule.verified_on = { ...rule.verified_on, claude_version: "2.1.310" };
            rule.due = false;
          }
        },
      });
      expect(
        await screen.findByText(
          /Bar Tab checked 80 rules on an older version, so they may be out of date/,
        ),
      ).toBeVisible();
    });

    it("says every rule is due, in the some form, when their versions differ", async () => {
      await open("", {
        installed: "2.1.310",
        mutate: (rules) => {
          const first = rules[0];
          if (first !== undefined)
            first.verified_on = { ...first.verified_on, claude_version: "2.1.305" };
        },
      });
      expect(await screen.findByText(/Bar Tab checked 84 rules on an older version/)).toBeVisible();
    });

    it("shows nothing when no rule is due", async () => {
      await open();
      await screen.findByRole("navigation", { name: en.sf_settings });
      expect(screen.queryByText(/You run Claude Code/)).toBeNull();
    });

    it("shows only due rules in the due view, with its notice and Show all", async () => {
      const user = userEvent.setup();
      await open("?due=1", {
        installed: "2.1.310",
        mutate: (rules) => {
          for (const rule of rules.slice(0, 4)) {
            rule.verified_on = { ...rule.verified_on, claude_version: "2.1.310" };
            rule.due = false;
          }
        },
      });
      expect(
        await screen.findByText(
          /Showing the 80 rules Bar Tab checked on a version older than your 2\.1\.310/,
        ),
      ).toBeVisible();
      expect(screen.getByText("80 of 84 rules", { selector: "p" })).toBeVisible();
      // No row carries the due mark inside the due view.
      expect(screen.queryByText(en.dc_due_mark)).toBeNull();
      await user.click(screen.getByRole("link", { name: en.dc_due_show_all }));
      await waitFor(() => {
        expect(hash()).toBe("#/reference/decides");
      });
    });

    it("counts the due view as 84 rules, not 84 of 84, when every rule is due", async () => {
      await open("?due=1", { installed: "2.1.310" });
      expect(await screen.findByText("84 rules", { selector: "p" })).toBeVisible();
      expect(screen.queryByText("84 of 84 rules", { selector: "p" })).toBeNull();
    });

    it("draws the notice's Unknown as the status chip, at rest and in the due view", async () => {
      await open("", { installed: "2.1.310" });
      const rest = (await screen.findByText(/Bar Tab checked all 84 rules/)).closest("p");
      const chip = within(rest as HTMLElement).getByText(en.status_unknown);
      expect(chip).toHaveClass("status-chip", "status-chip-unknown");
      cleanup();
      await open("?due=1", { installed: "2.1.310" });
      const due = (await screen.findByText(/Showing all 84 rules/)).closest("p");
      expect(within(due as HTMLElement).getByText(en.status_unknown)).toHaveClass(
        "status-chip-unknown",
      );
    });

    it("marks a due row only when some rules are due, never when all are", async () => {
      await open("", {
        installed: "2.1.310",
        mutate: (rules) => {
          for (const rule of rules.slice(0, 4)) {
            rule.verified_on = { ...rule.verified_on, claude_version: "2.1.310" };
            rule.due = false;
          }
        },
      });
      await screen.findByRole("navigation", { name: en.sf_settings });
      expect(screen.getAllByText(en.dc_due_mark).length).toBeGreaterThan(0);
      cleanup();
      await open("", { installed: "2.1.310" });
      await screen.findByRole("navigation", { name: en.sf_settings });
      expect(screen.queryByText(en.dc_due_mark)).toBeNull();
    });

    it("says no rules are due, and Show all leaves the view", async () => {
      const user = userEvent.setup();
      await open("?due=1");
      expect(await screen.findByRole("heading", { name: en.dc_due_none_h })).toBeVisible();
      expect(screen.getByText(t("dc_due_none_b", { installed: "2.1.302" }))).toBeVisible();
      await user.click(screen.getByRole("button", { name: en.dc_due_show_all }));
      expect(await screen.findByRole("navigation", { name: en.sf_settings })).toBeVisible();
      expect(hash()).toBe("#/reference/decides");
    });

    it("says no rules are due when the Confidence filter leaves none of the due ones", async () => {
      await open("?due=1&confidence=assumed", {
        installed: "2.1.310",
        mutate: (rules) => {
          for (const rule of rules) {
            if (rule.confidence === "assumed") {
              rule.verified_on = { ...rule.verified_on, claude_version: "2.1.310" };
              rule.due = false;
            }
          }
        },
      });
      expect(await screen.findByRole("heading", { name: en.dc_due_none_h })).toBeVisible();
    });
  });

  describe("phones", () => {
    it("makes the list the page, and a setting its own page with a back link", async () => {
      const user = userEvent.setup();
      await open("", {}, 375);
      const nav = await screen.findByRole("navigation", { name: en.sf_settings });
      expect(screen.queryByRole("region", { name: /Effort level/ })).toBeNull();
      await user.click(within(nav).getByRole("link", { name: /Cache lifetime/ }));
      const page = await screen.findByRole("region", { name: settingName("promptCacheTtl") });
      expect(screen.queryByRole("navigation", { name: en.sf_settings })).toBeNull();
      const back = within(page).getByRole("link", {
        name: new RegExp(t("sp_back", { part: en.sf_settings })),
      });
      await user.click(back);
      const list = await screen.findByRole("navigation", { name: en.sf_settings });
      // Focus and scroll return to the setting's row.
      await waitFor(() => {
        expect(within(list).getByRole("link", { name: /Cache lifetime/ })).toHaveFocus();
      });
    });

    it("shows the results alone while searching", async () => {
      await open("?q=cache", {}, 375);
      await screen.findByRole("region", { name: /rules in \d+ settings$/ });
      expect(screen.queryByRole("navigation", { name: en.sf_settings })).toBeNull();
    });
  });
});
