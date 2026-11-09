import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Card, states } from "./Card";

afterEach(cleanup);

describe("Card", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "header-extras", "foot"]);
  });

  it("is a region labelled by its h2", () => {
    render(<Card title="Model check">Body</Card>);
    expect(screen.getByRole("region", { name: "Model check" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Model check" })).toBeInTheDocument();
  });

  it("renders count, question, right slot and foot when given", () => {
    render(
      <Card title="T" count="4" question="Did it run?" right={<span>Right</span>} foot="Foot note">
        Body
      </Card>,
    );
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Did it run?")).toBeInTheDocument();
    expect(screen.getByText("Right")).toBeInTheDocument();
    expect(screen.getByText("Foot note")).toBeInTheDocument();
  });
});
