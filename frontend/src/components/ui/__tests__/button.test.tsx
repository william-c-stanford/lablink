/**
 * Button component tests
 *
 * Covers:
 *  - Renders all variants (primary, secondary, ghost, danger, outline)
 *  - Renders all sizes
 *  - Disabled state: aria attribute, cursor, no interaction
 *  - Loading state: spinner shown, button disabled
 *  - leftIcon / rightIcon rendered
 *  - onClick fires
 *  - Shadow tokens present in class names for each variant
 *  - Proper ARIA attributes
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "../button";

describe("Button — variants", () => {
  it("renders a secondary button by default", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole("button", { name: "Click me" });
    expect(btn).toBeInTheDocument();
    // default background is nm surface grey
    expect(btn.className).toContain("bg-[#f5f7fa]");
  });

  it("renders a primary button with blue background", () => {
    render(<Button variant="primary">Primary</Button>);
    const btn = screen.getByRole("button", { name: "Primary" });
    expect(btn.className).toContain("bg-[#3b82f6]");
    expect(btn.className).toContain("text-white");
  });

  it("renders a ghost button with transparent background", () => {
    render(<Button variant="ghost">Ghost</Button>);
    const btn = screen.getByRole("button", { name: "Ghost" });
    expect(btn.className).toContain("bg-transparent");
  });

  it("renders a danger button with red background", () => {
    render(<Button variant="danger">Delete</Button>);
    const btn = screen.getByRole("button", { name: "Delete" });
    expect(btn.className).toContain("bg-[#ef4444]");
    expect(btn.className).toContain("text-white");
  });

  it("renders an outline button with inset shadow", () => {
    render(<Button variant="outline">Outline</Button>);
    const btn = screen.getByRole("button", { name: "Outline" });
    expect(btn.className).toContain("bg-[#f5f7fa]");
    expect(btn.className).toContain("text-[#3b82f6]");
    // inset shadow token present
    expect(btn.className).toContain("inset_3px_3px_6px");
  });
});

describe("Button — sizes", () => {
  const sizes = ["xs", "sm", "md", "lg", "xl", "icon"] as const;

  sizes.forEach((size) => {
    it(`renders size="${size}"`, () => {
      render(
        <Button size={size}>
          {size !== "icon" ? size : <span>i</span>}
        </Button>,
      );
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });
});

describe("Button — shadow depth states", () => {
  it("primary has nm-glow-blue shadow token", () => {
    render(<Button variant="primary">CTA</Button>);
    const btn = screen.getByRole("button");
    // The blue glow rgba
    expect(btn.className).toContain("rgba(59,130,246");
  });

  it("secondary has nm-btn outset shadow token", () => {
    render(<Button variant="secondary">Secondary</Button>);
    const btn = screen.getByRole("button");
    // 4px outset shadow
    expect(btn.className).toContain("4px_4px_8px");
  });

  it("active state class uses inset shadow", () => {
    render(<Button variant="secondary">Secondary</Button>);
    const btn = screen.getByRole("button");
    // active pseudo-class uses inset shadow — check the active: class is declared
    expect(btn.className).toContain("active:[box-shadow:inset");
  });
});

describe("Button — disabled state", () => {
  it("is not interactive when disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Disabled
      </Button>,
    );
    const btn = screen.getByRole("button", { name: "Disabled" });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("has opacity class when disabled", () => {
    render(<Button disabled>Disabled</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("disabled:opacity-45");
  });
});

describe("Button — loading state", () => {
  it("shows spinner and is disabled when loading", () => {
    render(<Button loading>Submit</Button>);
    const btn = screen.getByRole("button", { name: "Submit" });
    expect(btn).toBeDisabled();
    // spinner has animate-spin
    const spinner = btn.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();
  });

  it("hides leftIcon when loading", () => {
    render(
      <Button loading leftIcon={<span data-testid="icon">→</span>}>
        Submit
      </Button>,
    );
    expect(screen.queryByTestId("icon")).not.toBeInTheDocument();
  });
});

describe("Button — icons", () => {
  it("renders leftIcon before children", () => {
    render(
      <Button leftIcon={<span data-testid="left">←</span>}>Go back</Button>,
    );
    expect(screen.getByTestId("left")).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveTextContent("Go back");
  });

  it("renders rightIcon after children", () => {
    render(
      <Button rightIcon={<span data-testid="right">→</span>}>Next</Button>,
    );
    expect(screen.getByTestId("right")).toBeInTheDocument();
  });
});

describe("Button — interaction", () => {
  it("fires onClick when clicked", () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Click me</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("forwards ref to button element", () => {
    const ref = { current: null } as unknown as React.RefObject<HTMLButtonElement>;
    render(<Button ref={ref}>Ref</Button>);
    expect(ref.current).not.toBeNull();
    expect(ref.current?.tagName).toBe("BUTTON");
  });
});

describe("Button — custom className", () => {
  it("merges custom className with default classes", () => {
    render(<Button className="custom-cls">Custom</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("custom-cls");
  });
});
