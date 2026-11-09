import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PageHeader, states } from "./PageHeader";

afterEach(cleanup);

describe("PageHeader", () => {
  it("lists every state", () => {
    expect(states).toContain("with-breadcrumb");
  });

  it("renders the h1, sub line and controls", () => {
    render(<PageHeader title="Your setup" sub="What loads" controls={<button>Range</button>} />);
    expect(screen.getByRole("heading", { level: 1, name: "Your setup" })).toBeInTheDocument();
    expect(screen.getByText("What loads")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Range" })).toBeInTheDocument();
  });

  it("renders a breadcrumb nav whose last item is the current page", () => {
    render(
      <PageHeader
        title="Effort"
        breadcrumb={{
          label: "Breadcrumb",
          items: [
            { label: "Your setup", href: "#/setup" },
            { label: "Effort", href: "#/setup/effort" },
          ],
        }}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your setup" })).toHaveAttribute("href", "#/setup");
    expect(screen.getByRole("link", { name: "Effort" })).toHaveAttribute("aria-current", "page");
  });
});
