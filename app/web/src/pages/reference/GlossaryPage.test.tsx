import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { takeReturnFocus } from "@/components/HelpEntry/origin";
import { en } from "@/strings/en";
import { GLOSSARY } from "@/strings/glossary";
import { CONFIDENCE_WORDS, SCOPES, STATUS_WORDS } from "@/strings/lists";
import { t } from "@/strings/t";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { fakeServer } from "@/test/server";

beforeAll(() => {
  // jsdom has no scrollIntoView.
  Element.prototype.scrollIntoView = () => undefined;
});

/** The first of a list, or a failure with a name, so a test never leans on a non-null assertion. */
function first<T>(list: readonly T[]): T {
  const [found] = list;
  if (found === undefined) throw new Error("the list is empty");
  return found;
}

afterEach(() => {
  cleanup();
  resetViewport();
  postStatus("");
  takeReturnFocus();
});

const sleep = (ms: number) =>
  act(async () => {
    await new Promise((done) => setTimeout(done, ms));
  });

async function open(path = "", width = 1440) {
  const server = fakeServer();
  const view = await mount(`#/reference/glossary${path}`, { server, width });
  await screen.findByRole("heading", { level: 1, name: en.nav_glossary });
  return { ...view, server };
}

const TERM_COUNT = Object.values(GLOSSARY).filter((term) => term.group === "terms").length;
const LIST_COUNT = STATUS_WORDS.length + SCOPES.length + CONFIDENCE_WORDS.length;
const ENTRIES = TERM_COUNT + LIST_COUNT;

function announcer(): HTMLElement {
  const found = screen.getAllByRole("status").find((region) => region.closest(".search") !== null);
  if (found === undefined) throw new Error("no search status region");
  return found;
}

/** The dt of an entry, by the id a route names. */
function term(id: string): HTMLElement {
  const found = Array.from(document.querySelectorAll<HTMLElement>("[data-term-id]")).find(
    (el) => el.dataset.termId === id,
  );
  if (found === undefined) throw new Error(`no entry ${id}`);
  return found;
}

describe("Glossary", () => {
  describe("the rest state", () => {
    it("has the three lists first and then the terms, each with its count and question", async () => {
      await open();
      const sections = screen.getAllByRole("region");
      expect(
        sections.map((section) => within(section).getByRole("heading", { level: 2 }).textContent),
      ).toEqual([
        GLOSSARY["status-words"].term,
        GLOSSARY.scopes.term,
        GLOSSARY["confidence-words"].term,
        en.gl_terms_h,
      ]);
      const counts = sections.map((section) => section.querySelector(".card-count")?.textContent);
      expect(counts).toEqual(["7", "7", "3", String(TERM_COUNT)]);
      expect(screen.getByText(en.gl_status_q)).toBeVisible();
      expect(screen.getByText(en.gl_scopes_q)).toBeVisible();
      expect(screen.getByText(en.gl_conf_q)).toBeVisible();
      expect(screen.getByText(en.gl_terms_q)).toBeVisible();
    });

    it("draws each status word as its chip with its meaning, and the words once", async () => {
      await open();
      const status = screen.getByRole("region", { name: GLOSSARY["status-words"].term });
      for (const item of STATUS_WORDS) {
        const dt = term(`status-${item.id}`);
        expect(dt.querySelector(".status-chip")).toHaveTextContent(en[item.word]);
        expect(dt.nextElementSibling).toHaveTextContent(en[item.means]);
        expect(status).toContainElement(dt);
      }
    });

    it("lists the scopes in lists.ts order and the confidence words as badges", async () => {
      await open();
      const scopes = screen.getByRole("region", { name: GLOSSARY.scopes.term });
      expect(
        within(scopes)
          .getAllByRole("term")
          .map((dt) => dt.textContent),
      ).toEqual(SCOPES.map((item) => en[item.word]));
      for (const item of CONFIDENCE_WORDS) {
        const dt = term(`confidence-${item.id}`);
        expect(dt.querySelector(".badge")).toHaveTextContent(en[item.word]);
        expect(dt.nextElementSibling).toHaveTextContent(en[item.means]);
      }
    });

    it("lists the terms from A to Z, with each term's see links", async () => {
      await open();
      const terms = screen.getByRole("region", { name: en.gl_terms_h });
      const names = within(terms)
        .getAllByRole("term")
        .map((dt) => dt.textContent ?? "");
      expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, "en")));
      expect(names).toHaveLength(TERM_COUNT);
      const dd = term("cache-write").nextElementSibling as HTMLElement;
      // The label starts the related links, in the same row.
      const see = dd.querySelector(".ref-see");
      expect(see?.firstElementChild).toHaveTextContent(en.gl_see);
      expect(see?.firstElementChild?.nextElementSibling).toContainElement(
        within(dd).getByRole("link", { name: GLOSSARY["cost-kinds"].term }),
      );
      expect(within(dd).getByRole("link", { name: GLOSSARY["cost-kinds"].term })).toHaveAttribute(
        "href",
        "#/reference/glossary/cost-kinds",
      );
    });

    it("has Jump to chips that name each section with its count", async () => {
      const user = userEvent.setup();
      await open();
      expect(screen.getByText(en.sp_jump)).toBeVisible();
      const chip = screen.getByRole("button", {
        name: new RegExp(`^${en.gl_terms_h} ${String(TERM_COUNT)}$`),
      });
      await user.click(chip);
      expect(screen.getByRole("heading", { level: 2, name: en.gl_terms_h })).toHaveFocus();
    });

    it("has no help spots, no loading state and no API call", async () => {
      const { server } = await open();
      expect(screen.getByRole("main").querySelector("[data-help-id]")).toBeNull();
      expect(screen.queryByText(en.dc_loading)).toBeNull();
      expect(server.calls.filter((path) => path.startsWith("/api/rules"))).toEqual([]);
    });

    it("leaves focus on the h1 for a plain load", async () => {
      await open();
      await waitFor(() => {
        expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
      });
    });
  });

  describe("search", () => {
    it("narrows every section and counts the entries, in the URL and the line", async () => {
      const user = userEvent.setup();
      await open();
      await user.type(screen.getByRole("searchbox", { name: en.gl_search_label }), "cache");
      expect(window.location.hash).toBe("#/reference/glossary?q=cache");
      const shown = document.querySelectorAll("[data-term-id]").length;
      expect(shown).toBeGreaterThan(0);
      expect(shown).toBeLessThan(ENTRIES);
      expect(
        screen.getByText(`${String(shown)} of ${String(ENTRIES)} entries`, { selector: "p" }),
      ).toBeVisible();
      expect(document.querySelectorAll("mark").length).toBeGreaterThan(0);
      // Jump to goes while searching.
      expect(screen.queryByText(en.sp_jump)).toBeNull();
    });

    it("announces once after typing settles, and not on load", async () => {
      const user = userEvent.setup();
      await open();
      expect(announcer()).toBeEmptyDOMElement();
      await user.type(screen.getByRole("searchbox", { name: en.gl_search_label }), "cache");
      expect(announcer()).toBeEmptyDOMElement();
      const shown = document.querySelectorAll("[data-term-id]").length;
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(
            `${String(shown)} of ${String(ENTRIES)} entries shown`,
          );
        },
        { timeout: 1500 },
      );
      await user.click(first(screen.getAllByRole("button", { name: en.sf_clear })));
      await waitFor(
        () => {
          expect(announcer()).toHaveTextContent(`${String(ENTRIES)} entries shown`);
        },
        { timeout: 1500 },
      );
    });

    it("says nothing on load when the URL already holds a query", async () => {
      await open("?q=cache");
      await sleep(900);
      expect(announcer()).toBeEmptyDOMElement();
    });

    it("has a no-results card with Clear search and a link to the rules, with the query", async () => {
      const user = userEvent.setup();
      await open("?q=teleportation");
      expect(
        await screen.findByRole("heading", { name: t("gl_none_h", { query: "teleportation" }) }),
      ).toBeVisible();
      expect(screen.getByText(en.gl_none_b)).toBeVisible();
      expect(
        screen.getByRole("link", { name: t("gl_none_rules", { query: "teleportation" }) }),
      ).toHaveAttribute("href", "#/reference/decides?q=teleportation");
      expect(announcer()).toBeEmptyDOMElement();
      await user.click(
        first(
          within(screen.getByRole("main")).getAllByRole("button", { name: en.sf_clear }).reverse(),
        ),
      );
      await waitFor(() => {
        expect(window.location.hash).toBe("#/reference/glossary");
      });
      expect(await screen.findByRole("region", { name: en.gl_terms_h })).toBeVisible();
    });
  });

  describe("routes", () => {
    it("marks and focuses a term, and scrolls to it", async () => {
      await open("/cache-write");
      const dt = term("cache-write");
      expect(dt).toHaveAttribute("aria-current", "true");
      expect(dt.parentElement).toHaveClass("ref-term-on");
      await waitFor(() => {
        expect(document.activeElement).toBe(dt);
      });
    });

    it("gives each status word, scope and confidence word its own target", async () => {
      for (const id of ["status-in_effect", "scope-managed", "scope-shell", "confidence-tested"]) {
        const { unmount } = await openUnmountable(`/${id}`);
        await waitFor(() => {
          expect(document.activeElement).toBe(term(id));
        });
        expect(term(id).parentElement).toHaveClass("ref-term-on");
        unmount();
      }
    });

    it("lands on the Status words section from its help link", async () => {
      await open("/status-words");
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { level: 2, name: GLOSSARY["status-words"].term }),
        ).toHaveFocus();
      });
    });

    it("focuses a section heading for a section term", async () => {
      await open("/scopes");
      await waitFor(() => {
        expect(screen.getByRole("heading", { level: 2, name: GLOSSARY.scopes.term })).toHaveFocus();
      });
    });

    it("moves between terms by their see links and keeps one route", async () => {
      const user = userEvent.setup();
      await open("/cache-write");
      const dd = term("cache-write").nextElementSibling as HTMLElement;
      await user.click(within(dd).getByRole("link", { name: GLOSSARY["cost-kinds"].term }));
      await waitFor(() => {
        expect(document.activeElement).toBe(term("cost-kinds"));
      });
      expect(window.location.hash).toBe("#/reference/glossary/cost-kinds");
    });

    it("still shows a target the query would hide", async () => {
      await open("/cache-write?q=teleportation");
      expect(term("cache-write")).toBeVisible();
      expect(document.querySelectorAll("[data-term-id]")).toHaveLength(1);
    });

    it("says a stale id is gone and links to the whole Glossary", async () => {
      await open("/no-such-term");
      expect(
        await screen.findByRole("heading", { name: t("gl_gone_h", { id: "no-such-term" }) }),
      ).toBeVisible();
      expect(screen.getByText(en.sp_gone_b)).toBeVisible();
      const link = screen.getByRole("link", { name: t("sp_back", { part: en.nav_glossary }) });
      expect(link).toHaveAttribute("href", "#/reference/glossary");
      await waitFor(() => {
        expect(link).toHaveFocus();
      });
    });

    it("sends a path with too many segments to the picker", async () => {
      const server = fakeServer();
      await mount("#/reference/glossary/a/b", { server });
      await waitFor(() => {
        expect(window.location.hash).toBe("#/");
      });
    });
  });

  describe("Back to the page a help link came from", () => {
    const from = encodeURIComponent("/p/builder/review/sessions");

    it("shows Back to {page} with the origin's nav name, and carries the origin on see links", async () => {
      await open(`/cache-write?from=${from}&help=sessions.cols`);
      const back = screen.getByRole("link", {
        name: new RegExp(t("sp_back", { part: en.nav_sessions })),
      });
      expect(back).toHaveAttribute("href", "#/p/builder/review/sessions");
      const dd = term("cache-write").nextElementSibling as HTMLElement;
      const see = within(dd).getAllByRole("link")[0];
      expect(see?.getAttribute("href")).toContain(`from=${from}`);
      expect(see?.getAttribute("href")).toContain("help=sessions.cols");
    });

    it("uses the parent page's name for a detail page", async () => {
      const cases: [string, string][] = [
        ["/p/builder/review/sessions/s1", en.nav_sessions],
        ["/p/builder/review/agents/new", en.nav_agents],
        ["/p/builder/setup/settings/effortLevel", en.nav_setup],
        ["/p/builder/live", en.nav_live],
      ];
      for (const [route, name] of cases) {
        const { unmount } = await openUnmountable(`?from=${encodeURIComponent(route)}&help=x`);
        expect(
          screen.getByRole("link", { name: new RegExp(t("sp_back", { part: name })) }),
        ).toHaveAttribute("href", `#${route}`);
        unmount();
      }
    });

    it("shows no Back link for an origin that is not a page, or is a Reference page", async () => {
      await open(`?from=${encodeURIComponent("/nowhere")}&help=x`);
      expect(screen.queryByRole("link", { name: /Back to/ })).toBeNull();
      cleanup();
      await open(`?from=${encodeURIComponent("/reference/decides")}&help=x`);
      expect(screen.queryByRole("link", { name: /Back to/ })).toBeNull();
      cleanup();
      await open("");
      expect(screen.queryByRole("link", { name: /Back to/ })).toBeNull();
    });

    it("holds the help id for the next page when Back is pressed", async () => {
      const user = userEvent.setup();
      await open(`/cache-write?from=${from}&help=sessions.cols`);
      await user.click(within(screen.getByRole("main")).getByRole("link", { name: /Back to/ }));
      await waitFor(() => {
        expect(window.location.hash).toBe("#/p/builder/review/sessions");
      });
    });

    it("focuses the trigger once the page it names has it, and the h1 when it never does", async () => {
      const user = userEvent.setup();
      await open(`/cache-write?from=${encodeURIComponent("/p/builder/to-fix")}&help=to-fix.test`);
      await user.click(within(screen.getByRole("main")).getByRole("link", { name: /Back to/ }));
      const main = await screen.findByRole("main");
      await screen.findByRole("heading", { level: 1, name: en.nav_tofix });
      // The page puts the "?" in later, as a page with data does.
      const trigger = document.createElement("button");
      trigger.dataset.helpId = "to-fix.test";
      trigger.textContent = "?";
      await act(async () => {
        main.appendChild(trigger);
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(document.activeElement).toBe(trigger);
      });
    });

    it("leaves focus on the h1 when the trigger is gone", async () => {
      const user = userEvent.setup();
      await open(`/cache-write?from=${encodeURIComponent("/p/builder/to-fix")}&help=gone.trigger`);
      await user.click(within(screen.getByRole("main")).getByRole("link", { name: /Back to/ }));
      const h1 = await screen.findByRole("heading", { level: 1, name: en.nav_tofix });
      await sleep(100);
      expect(document.activeElement).toBe(h1);
    });
  });
});

async function openUnmountable(path: string) {
  const server = fakeServer();
  const view = await mount(`#/reference/glossary${path}`, { server });
  await screen.findByRole("heading", { level: 1, name: en.nav_glossary });
  return { unmount: cleanup, ...view };
}
