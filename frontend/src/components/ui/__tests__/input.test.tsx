/**
 * Input component tests
 *
 * Covers:
 *  - Renders input with nm-inset shadow
 *  - Accepts value and onChange
 *  - Error state: aria-invalid + red outline class
 *  - Disabled state
 *  - leftIcon / rightIcon wrapper
 *  - Textarea renders
 *  - InputGroup renders label + helper text
 *  - InputGroup error message
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Input, Textarea, InputGroup } from "../input";

describe("Input — rendering", () => {
  it("renders an input element", () => {
    render(<Input placeholder="Enter text" />);
    expect(screen.getByPlaceholderText("Enter text")).toBeInTheDocument();
  });

  it("has nm-inset CSS class applied", () => {
    render(<Input data-testid="inp" />);
    const inp = screen.getByTestId("inp");
    // nm-inset CSS class from index.css — ensures neuromorphic sunken shadow
    expect(inp.className).toContain("nm-inset");
  });

  it("has surface grey background", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("bg-[#f5f7fa]");
  });

  it("has rounded corners (neuromorphic radius)", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("rounded-2xl");
  });
});

describe("Input — controlled value", () => {
  it("shows typed value", () => {
    const onChange = vi.fn();
    render(<Input value="hello" onChange={onChange} />);
    const inp = screen.getByDisplayValue("hello") as HTMLInputElement;
    expect(inp.value).toBe("hello");
  });

  it("fires onChange on user input", () => {
    const onChange = vi.fn();
    render(<Input defaultValue="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "abc" },
    });
    expect(onChange).toHaveBeenCalled();
  });
});

describe("Input — error state", () => {
  it("sets aria-invalid when error=true", () => {
    render(<Input data-testid="inp" error />);
    expect(screen.getByTestId("inp")).toHaveAttribute("aria-invalid", "true");
  });

  it("applies red outline class when error=true", () => {
    render(<Input data-testid="inp" error />);
    expect(screen.getByTestId("inp").className).toContain("[outline:2px_solid_#ef4444]");
  });

  it("does not set aria-invalid when no error", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp")).not.toHaveAttribute("aria-invalid");
  });
});

describe("Input — disabled state", () => {
  it("is disabled when disabled=true", () => {
    render(<Input disabled />);
    const inp = screen.getByRole("textbox");
    expect(inp).toBeDisabled();
  });

  it("has disabled opacity class", () => {
    render(<Input data-testid="inp" disabled />);
    expect(screen.getByTestId("inp").className).toContain("disabled:opacity-45");
  });
});

describe("Input — icon wrappers", () => {
  it("renders wrapper div when leftIcon provided", () => {
    const { container } = render(
      <Input leftIcon={<span data-testid="icon">🔍</span>} />,
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
    // wrapper div present
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.tagName).toBe("DIV");
  });

  it("renders wrapper div when rightIcon provided", () => {
    const { container } = render(
      <Input rightIcon={<span data-testid="right-icon">✓</span>} />,
    );
    expect(screen.getByTestId("right-icon")).toBeInTheDocument();
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.tagName).toBe("DIV");
  });

  it("renders directly (no wrapper) when no icons", () => {
    const { container } = render(<Input data-testid="inp" />);
    expect(container.firstChild?.nodeName).toBe("INPUT");
  });
});

describe("Textarea — rendering", () => {
  it("renders a textarea element", () => {
    render(<Textarea placeholder="Type here…" />);
    expect(screen.getByPlaceholderText("Type here…").tagName).toBe("TEXTAREA");
  });

  it("has nm-inset CSS class applied", () => {
    render(<Textarea data-testid="ta" />);
    expect(screen.getByTestId("ta").className).toContain("nm-inset");
  });

  it("has error styling when error=true", () => {
    render(<Textarea data-testid="ta" error />);
    const ta = screen.getByTestId("ta");
    expect(ta).toHaveAttribute("aria-invalid", "true");
    expect(ta.className).toContain("[outline:2px_solid_#ef4444]");
  });
});

describe("InputGroup — composition", () => {
  it("renders label text", () => {
    render(
      <InputGroup label="Email" htmlFor="email">
        <Input id="email" />
      </InputGroup>,
    );
    expect(screen.getByText("Email")).toBeInTheDocument();
  });

  it("renders required asterisk when required=true", () => {
    render(
      <InputGroup label="Name" required>
        <Input />
      </InputGroup>,
    );
    expect(screen.getByText("*")).toBeInTheDocument();
  });

  it("renders helperText", () => {
    render(
      <InputGroup helperText="We'll never share your email.">
        <Input />
      </InputGroup>,
    );
    expect(screen.getByText("We'll never share your email.")).toBeInTheDocument();
  });

  it("renders errorMessage with role=alert", () => {
    render(
      <InputGroup errorMessage="This field is required.">
        <Input />
      </InputGroup>,
    );
    const msg = screen.getByRole("alert");
    expect(msg).toHaveTextContent("This field is required.");
    expect(msg.className).toContain("text-[#ef4444]");
  });

  it("prefers errorMessage over helperText", () => {
    render(
      <InputGroup helperText="Helper" errorMessage="Error!">
        <Input />
      </InputGroup>,
    );
    expect(screen.queryByText("Helper")).not.toBeInTheDocument();
    expect(screen.getByText("Error!")).toBeInTheDocument();
  });
});
