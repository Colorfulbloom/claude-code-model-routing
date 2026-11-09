import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MoreCard, states } from "./MoreCard";

afterEach(cleanup);

describe("MoreCard", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "focus"]);
  });

  it("is a named region with one link per row", () => {
    render(
      <MoreCard
        title="Reference"
        rows={[
          { id: "a", href: "#/a", label: "How Claude Code decides", icon: "decides" },
          { id: "b", href: "#/b", label: "Glossary", icon: "glossary", className: "is-focus" },
        ]}
      />,
    );
    const region = screen.getByRole("region", { name: "Reference" });
    const links = within(region).getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName("How Claude Code decides");
    expect(links[1]).toHaveClass("is-focus");
  });
});
