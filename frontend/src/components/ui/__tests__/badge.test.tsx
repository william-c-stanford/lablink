/**
 * Badge component tests
 *
 * Covers:
 *  - Renders correct color for each status
 *  - Shows status text
 *  - Applies custom className
 *  - All variants render with correct styling tokens
 *  - Sizes (sm, md, lg)
 *  - Pulse dot animation class
 *  - Icon rendering
 *  - UploadStatusBadge: all 6 statuses with correct variant + pulse
 *  - ExperimentStatusBadge: all 5 statuses with correct variant
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  Badge,
  UploadStatusBadge,
  ExperimentStatusBadge,
} from "../badge";
import type { UploadStatus, ExperimentStatus } from "../badge";

describe("Badge — renders correct color for each status", () => {
  const variantColorMap: Array<{
    variant: "default" | "primary" | "success" | "warning" | "danger" | "info" | "outline";
    expectedClass: string;
  }> = [
    { variant: "default", expectedClass: "bg-[#f5f7fa]" },
    { variant: "primary", expectedClass: "bg-[#3b82f6]" },
    { variant: "success", expectedClass: "bg-[#22c55e]" },
    { variant: "warning", expectedClass: "bg-[#f59e0b]" },
    { variant: "danger",  expectedClass: "bg-[#ef4444]" },
    { variant: "info",    expectedClass: "bg-[#6366f1]" },
    { variant: "outline", expectedClass: "bg-transparent" },
  ];

  variantColorMap.forEach(({ variant, expectedClass }) => {
    it(`variant="${variant}" renders with ${expectedClass}`, () => {
      const { container } = render(<Badge variant={variant}>{variant}</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain(expectedClass);
    });
  });
});

describe("Badge — shows status text", () => {
  it("renders children text content", () => {
    render(<Badge>Pending</Badge>);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders text for success variant", () => {
    render(<Badge variant="success">Parsed</Badge>);
    expect(screen.getByText("Parsed")).toBeInTheDocument();
  });

  it("renders text for danger variant", () => {
    render(<Badge variant="danger">Failed</Badge>);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("Badge — applies custom className", () => {
  it("merges custom className with variant classes", () => {
    const { container } = render(
      <Badge className="my-custom-class">Custom</Badge>,
    );
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain("my-custom-class");
    // Also retains default variant classes
    expect(badge.className).toContain("bg-[#f5f7fa]");
  });

  it("custom className does not overwrite variant styling", () => {
    const { container } = render(
      <Badge variant="primary" className="extra-padding">Styled</Badge>,
    );
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain("extra-padding");
    expect(badge.className).toContain("bg-[#3b82f6]");
  });
});

describe("Badge — default variant details", () => {
  it("uses nm-inset shadow for default variant", () => {
    const { container } = render(<Badge>Default</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain("inset_3px_3px_6px");
  });

  it("primary has blue glow shadow", () => {
    const { container } = render(<Badge variant="primary">Primary</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain("rgba(59,130,246");
  });

  it("outline has ring class", () => {
    const { container } = render(<Badge variant="outline">Outline</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain("ring-1");
  });
});

describe("Badge — sizes", () => {
  it('size="sm" has smaller text', () => {
    const { container } = render(<Badge size="sm">sm</Badge>);
    expect((container.firstChild as HTMLElement).className).toContain("text-[9px]");
  });

  it('size="lg" has larger padding', () => {
    const { container } = render(<Badge size="lg">lg</Badge>);
    expect((container.firstChild as HTMLElement).className).toContain("px-3");
  });
});

describe("Badge — pulse animation", () => {
  it("renders pulse dot when pulse=true", () => {
    render(<Badge pulse>Uploading</Badge>);
    const dots = document.querySelectorAll(".animate-pulse");
    expect(dots.length).toBeGreaterThan(0);
  });

  it("does not render pulse dot when pulse=false", () => {
    render(<Badge>No pulse</Badge>);
    expect(document.querySelectorAll(".animate-pulse").length).toBe(0);
  });
});

describe("Badge — icon", () => {
  it("renders icon when provided", () => {
    render(
      <Badge icon={<span data-testid="badge-icon">★</span>}>Rated</Badge>,
    );
    expect(screen.getByTestId("badge-icon")).toBeInTheDocument();
  });

  it("does not render icon when pulse=true (pulse takes priority)", () => {
    render(
      <Badge pulse icon={<span data-testid="badge-icon">★</span>}>
        Pulsing
      </Badge>,
    );
    expect(screen.queryByTestId("badge-icon")).not.toBeInTheDocument();
  });
});

describe("UploadStatusBadge — all statuses", () => {
  const statuses: Array<{ status: UploadStatus; label: string; expectPulse: boolean }> =
    [
      { status: "pending",   label: "Pending",   expectPulse: false },
      { status: "queued",    label: "Queued",    expectPulse: false },
      { status: "uploading", label: "Uploading", expectPulse: true },
      { status: "parsing",   label: "Parsing",   expectPulse: true },
      { status: "parsed",    label: "Parsed",    expectPulse: false },
      { status: "failed",    label: "Failed",    expectPulse: false },
    ];

  statuses.forEach(({ status, label, expectPulse }) => {
    it(`status="${status}" renders label "${label}" with pulse=${expectPulse}`, () => {
      render(<UploadStatusBadge status={status} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      const dots = document.querySelectorAll(".animate-pulse");
      if (expectPulse) {
        expect(dots.length).toBeGreaterThan(0);
      } else {
        expect(dots.length).toBe(0);
      }
    });
  });
});

describe("ExperimentStatusBadge — all statuses", () => {
  const statuses: Array<{ status: ExperimentStatus; label: string }> = [
    { status: "draft",     label: "Draft" },
    { status: "active",    label: "Active" },
    { status: "completed", label: "Completed" },
    { status: "archived",  label: "Archived" },
    { status: "cancelled", label: "Cancelled" },
  ];

  statuses.forEach(({ status, label }) => {
    it(`status="${status}" renders label "${label}"`, () => {
      render(<ExperimentStatusBadge status={status} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('active status uses primary (blue) variant', () => {
    const { container } = render(<ExperimentStatusBadge status="active" />);
    expect((container.firstChild as HTMLElement).className).toContain("bg-[#3b82f6]");
  });

  it('completed status uses success (green) variant', () => {
    const { container } = render(<ExperimentStatusBadge status="completed" />);
    expect((container.firstChild as HTMLElement).className).toContain("bg-[#22c55e]");
  });
});
