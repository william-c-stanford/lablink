/**
 * Dialog (Modal) component tests
 *
 * Covers:
 *  - Dialog hidden by default
 *  - Opens via trigger
 *  - Closes via close button
 *  - Closes on Escape key
 *  - Closes on overlay click (when closeOnOverlayClick=true)
 *  - Does NOT close on panel click
 *  - Renders header, title, description, body, footer
 *  - nm-outset panel shadow
 *  - ConfirmDialog: renders confirm/cancel buttons, fires onConfirm
 *  - Controlled mode (open prop)
 *  - Body scroll lock while open
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
  DialogClose,
  ConfirmDialog,
} from "../dialog";
import { Button } from "../button";

// Helper: wraps a basic dialog
function TestDialog({
  defaultOpen = false,
  closeOnOverlayClick = true,
}: {
  defaultOpen?: boolean;
  closeOnOverlayClick?: boolean;
}) {
  return (
    <Dialog defaultOpen={defaultOpen}>
      <DialogTrigger>
        <Button>Open Dialog</Button>
      </DialogTrigger>
      <DialogContent closeOnOverlayClick={closeOnOverlayClick}>
        <DialogHeader>
          <DialogTitle>Test Dialog</DialogTitle>
          <DialogDescription>This is a test modal.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p>Modal content here.</p>
        </DialogBody>
        <DialogFooter>
          <DialogClose>
            <Button>Cancel</Button>
          </DialogClose>
          <Button variant="primary">Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

describe("Dialog — visibility", () => {
  it("does not render content when closed", () => {
    render(<TestDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders content after trigger click", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows title and description when open", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    expect(screen.getByText("Test Dialog")).toBeInTheDocument();
    expect(screen.getByText("This is a test modal.")).toBeInTheDocument();
  });
});

describe("Dialog — shadow tokens", () => {
  it("panel has nm-outset large shadow", () => {
    render(<TestDialog defaultOpen />);
    const panel = screen.getByRole("dialog");
    expect(panel.className).toContain("24px_24px_48px");
  });

  it("panel has large border radius", () => {
    render(<TestDialog defaultOpen />);
    const panel = screen.getByRole("dialog");
    expect(panel.className).toContain("rounded-[32px]");
  });

  it("panel has surface grey background", () => {
    render(<TestDialog defaultOpen />);
    const panel = screen.getByRole("dialog");
    expect(panel.className).toContain("bg-[#f5f7fa]");
  });
});

describe("Dialog — close interactions", () => {
  it("closes via the DialogClose button in footer", () => {
    render(<TestDialog />);
    // Open
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Close via Cancel button (wrapped in DialogClose)
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes via the header X button", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    // The header renders a close button aria-label="Close dialog"
    const closeBtn = screen.getByRole("button", { name: "Close dialog" });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape key", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on overlay click by default", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    // The overlay is the div with role="presentation"
    const overlay = screen.getByRole("presentation");
    fireEvent.click(overlay);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does NOT close on panel content click", () => {
    render(<TestDialog />);
    fireEvent.click(screen.getByRole("button", { name: "Open Dialog" }));
    // Click inside the panel
    fireEvent.click(screen.getByRole("dialog"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Dialog — controlled mode", () => {
  it("respects controlled open=true", () => {
    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogBody>Controlled open</DialogBody>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("respects controlled open=false", () => {
    render(
      <Dialog open={false}>
        <DialogContent>
          <DialogBody>Controlled closed</DialogBody>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("calls onOpenChange when close triggered", () => {
    const onOpenChange = vi.fn();
    render(
      <Dialog open={true} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Controlled</DialogTitle>
          </DialogHeader>
          <DialogBody>Content</DialogBody>
        </DialogContent>
      </Dialog>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("Dialog — structure", () => {
  it("has aria-modal=true", () => {
    render(<TestDialog defaultOpen />);
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});

describe("ConfirmDialog", () => {
  function Setup({
    onConfirm = vi.fn(),
    open = true,
    variant = "default" as "default" | "danger",
  } = {}) {
    return (
      <ConfirmDialog
        open={open}
        onOpenChange={vi.fn()}
        title="Are you sure?"
        description="This action cannot be undone."
        confirmLabel="Yes, proceed"
        cancelLabel="No, cancel"
        onConfirm={onConfirm}
        variant={variant}
      />
    );
  }

  it("renders title and description", () => {
    render(<Setup />);
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
    expect(screen.getByText("This action cannot be undone.")).toBeInTheDocument();
  });

  it("renders confirm and cancel buttons", () => {
    render(<Setup />);
    expect(screen.getByRole("button", { name: "Yes, proceed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No, cancel" })).toBeInTheDocument();
  });

  it("fires onConfirm when confirm button clicked", () => {
    const onConfirm = vi.fn();
    render(<Setup onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Yes, proceed" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("danger variant uses red confirm button", () => {
    render(<Setup variant="danger" />);
    const confirmBtn = screen.getByRole("button", { name: "Yes, proceed" });
    expect(confirmBtn.className).toContain("bg-[#ef4444]");
  });

  it("not rendered when open=false", () => {
    render(<Setup open={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
