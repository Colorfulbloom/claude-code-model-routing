import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Breadcrumb, states, type BreadcrumbProps } from "./Breadcrumb";

afterEach(cleanup);

const base: BreadcrumbProps = {
  label: "Breadcrumb",
  items: [
    { label: "Your setup", href: "#/setup" },
    { label: "Settings", href: "#/setup/settings" },
    { label: "Effort", href: "#/setup/settings/effort" },
  ],
};

describe("Breadcrumb", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "hover", "focus", "long", "hidden"]);
  });

  it("is a named nav with a link per crumb", () => {
    render(<Breadcrumb {...base} />);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your setup" })).toHaveAttribute("href", "#/setup");
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "#/setup/settings",
    );
  });

  it("marks only the last crumb as the current page", () => {
    render(<Breadcrumb {...base} />);
    expect(screen.getByRole("link", { name: "Effort" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Your setup" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Settings" })).not.toHaveAttribute("aria-current");
  });

  it("passes a forced-state class to one link", () => {
    render(
      <Breadcrumb
        {...base}
        items={[
          { label: "Your setup", href: "#/setup", className: "is-hover" },
          ...base.items.slice(1),
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Your setup" })).toHaveClass("is-hover");
  });

  it("leaves the trail out of the accessibility tree while hidden", () => {
    const { container } = render(<Breadcrumb {...base} hidden />);
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).toBeNull();
    const nav = container.querySelector("nav");
    expect(nav).toHaveAttribute("hidden");
    expect(nav).not.toBeVisible();
  });
});
