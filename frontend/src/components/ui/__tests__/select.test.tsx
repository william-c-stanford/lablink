/**
 * Select (NativeSelect) component tests
 *
 * Covers:
 *  - Renders select element
 *  - nm-inset shadow token
 *  - Placeholder option
 *  - Error state: aria-invalid + outline
 *  - Disabled state
 *  - leftIcon wrapper
 *  - ChevronDown icon present
 *  - Options render correctly
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Select, NativeSelect, SelectOption } from "../select";

describe("NativeSelect — rendering", () => {
  it("renders a select element", () => {
    render(
      <NativeSelect aria-label="Choose option">
        <SelectOption value="a">Option A</SelectOption>
      </NativeSelect>,
    );
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("has nm-inset shadow token", () => {
    render(<NativeSelect aria-label="test" />);
    const select = screen.getByRole("combobox");
    expect(select.className).toContain("inset_6px_6px_12px");
  });

  it("has surface grey background", () => {
    render(<NativeSelect aria-label="test" />);
    expect(screen.getByRole("combobox").className).toContain("bg-[#f5f7fa]");
  });

  it("has rounded corners", () => {
    render(<NativeSelect aria-label="test" />);
    expect(screen.getByRole("combobox").className).toContain("rounded-2xl");
  });
});

describe("NativeSelect — alias", () => {
  it("Select is an alias for NativeSelect", () => {
    render(
      <Select aria-label="alias-select">
        <SelectOption value="x">X</SelectOption>
      </Select>,
    );
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });
});

describe("NativeSelect — placeholder", () => {
  it("renders placeholder as first option when provided", () => {
    render(
      <NativeSelect placeholder="Choose…" aria-label="test">
        <SelectOption value="a">A</SelectOption>
      </NativeSelect>,
    );
    const opts = screen.getAllByRole("option");
    // First option is the placeholder
    expect(opts[0]).toHaveTextContent("Choose…");
  });

  it("placeholder option is disabled", () => {
    render(
      <NativeSelect placeholder="Choose…" aria-label="test">
        <SelectOption value="a">A</SelectOption>
      </NativeSelect>,
    );
    const placeholder = screen.getByText("Choose…").closest("option");
    expect(placeholder).toBeDisabled();
  });
});

describe("NativeSelect — error state", () => {
  it("sets aria-invalid when error=true", () => {
    render(<NativeSelect error aria-label="err-select" />);
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-invalid", "true");
  });

  it("applies red outline class when error=true", () => {
    render(<NativeSelect error aria-label="err-select" />);
    expect(screen.getByRole("combobox").className).toContain("[outline:2px_solid_#ef4444]");
  });
});

describe("NativeSelect — disabled state", () => {
  it("is disabled when disabled=true", () => {
    render(<NativeSelect disabled aria-label="disabled-select" />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });

  it("has disabled opacity class", () => {
    render(<NativeSelect disabled aria-label="disabled-select" />);
    expect(screen.getByRole("combobox").className).toContain("disabled:opacity-45");
  });
});

describe("NativeSelect — icon", () => {
  it("renders caret icon (ChevronDown) in wrapper", () => {
    const { container } = render(
      <NativeSelect aria-label="icon-select">
        <SelectOption value="a">A</SelectOption>
      </NativeSelect>,
    );
    // The wrapper div should contain an svg (ChevronDown)
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
  });

  it("renders wrapper div when leftIcon provided", () => {
    const { container } = render(
      <NativeSelect
        leftIcon={<span data-testid="left-icon">🔬</span>}
        aria-label="icon-select"
      >
        <SelectOption value="a">A</SelectOption>
      </NativeSelect>,
    );
    expect(screen.getByTestId("left-icon")).toBeInTheDocument();
    // Root is a div wrapper
    expect(container.firstChild?.nodeName).toBe("DIV");
  });
});

describe("NativeSelect — interaction", () => {
  it("calls onChange when value changes", () => {
    const onChange = vi.fn();
    render(
      <NativeSelect onChange={onChange} aria-label="select">
        <SelectOption value="a">A</SelectOption>
        <SelectOption value="b">B</SelectOption>
      </NativeSelect>,
    );
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "b" } });
    expect(onChange).toHaveBeenCalled();
  });
});
