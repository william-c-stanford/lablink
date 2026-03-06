/**
 * Spinner component tests
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Spinner } from "../spinner";

describe("Spinner", () => {
  it("renders with role=status", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-label", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Loading");
  });

  it("has animate-spin class", () => {
    render(<Spinner />);
    expect(screen.getByRole("status").className).toContain("animate-spin");
  });

  it('size="sm" applies smaller dimension classes', () => {
    render(<Spinner size="sm" />);
    expect(screen.getByRole("status").className).toContain("w-4");
  });

  it('size="lg" applies larger dimension classes', () => {
    render(<Spinner size="lg" />);
    expect(screen.getByRole("status").className).toContain("w-10");
  });

  it('color="white" applies white border', () => {
    render(<Spinner color="white" />);
    expect(screen.getByRole("status").className).toContain("border-white");
  });

  it('color="blue" (default) applies blue border', () => {
    render(<Spinner />);
    expect(screen.getByRole("status").className).toContain("border-[#3b82f6]");
  });
});
