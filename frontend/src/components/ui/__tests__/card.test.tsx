/**
 * Card component tests
 *
 * Covers:
 *  - Renders outset variant with correct shadow
 *  - Renders inset variant
 *  - Passes className through
 *  - flat variant has no shadow
 *  - hoverable adds transition classes
 *  - CardHeader, CardTitle, CardDescription, CardContent, CardFooter render
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "../card";

describe("Card — renders outset variant with correct shadow", () => {
  it("renders with nm-outset shadow by default", () => {
    const { container } = render(<Card data-testid="card" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("8px_8px_16px");
  });

  it("has surface grey background", () => {
    const { container } = render(<Card />);
    expect((container.firstChild as HTMLElement).className).toContain("bg-[#f5f7fa]");
  });

  it("has large border radius", () => {
    const { container } = render(<Card />);
    expect((container.firstChild as HTMLElement).className).toContain("rounded-[32px]");
  });
});

describe("Card — renders inset variant", () => {
  it("inset variant has nm-inset shadow", () => {
    const { container } = render(<Card variant="inset" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("inset_6px_6px_12px");
  });

  it("inset variant retains surface background", () => {
    const { container } = render(<Card variant="inset" />);
    expect((container.firstChild as HTMLElement).className).toContain("bg-[#f5f7fa]");
  });

  it("flat variant has no shadow class", () => {
    const { container } = render(<Card variant="flat" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("shadow-none");
  });
});

describe("Card — passes className through", () => {
  it("merges custom className with default classes", () => {
    const { container } = render(<Card className="my-custom" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("my-custom");
    expect(card.className).toContain("bg-[#f5f7fa]");
  });

  it("custom className on inset variant", () => {
    const { container } = render(
      <Card variant="inset" className="extra" />,
    );
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("extra");
    expect(card.className).toContain("inset_6px_6px_12px");
  });
});

describe("Card — hoverable", () => {
  it("adds scale transition when hoverable=true with outset variant", () => {
    const { container } = render(<Card hoverable />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain("hover:scale-[1.01]");
  });
});

describe("Card — composition", () => {
  it("renders CardTitle text", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>My Experiment</CardTitle>
        </CardHeader>
      </Card>,
    );
    expect(screen.getByText("My Experiment")).toBeInTheDocument();
  });

  it("renders CardDescription text", () => {
    render(
      <Card>
        <CardHeader>
          <CardDescription>Some description</CardDescription>
        </CardHeader>
      </Card>,
    );
    expect(screen.getByText("Some description")).toBeInTheDocument();
  });

  it("renders CardContent children", () => {
    render(
      <Card>
        <CardContent>
          <p>Body text</p>
        </CardContent>
      </Card>,
    );
    expect(screen.getByText("Body text")).toBeInTheDocument();
  });

  it("renders CardFooter with border-top separator", () => {
    const { container } = render(
      <Card>
        <CardFooter>
          <button>Action</button>
        </CardFooter>
      </Card>,
    );
    const footer = container.querySelector(".border-t");
    expect(footer).not.toBeNull();
  });
});
