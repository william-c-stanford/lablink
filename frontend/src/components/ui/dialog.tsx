/**
 * Dialog (Modal) — Neuromorphic modal primitive
 *
 * Design:
 *   - Overlay: semi-transparent slate + backdrop-blur
 *   - Panel: nm-outset with large shadow (24px), rounded-[32px]
 *   - Header/footer sections with faint dividers
 *   - Animated entry: fadeIn from slightly below
 *
 * Exports:
 *   Dialog         — root controller (provides context)
 *   DialogTrigger  — wraps trigger element
 *   DialogContent  — the modal panel
 *   DialogHeader   — styled header section
 *   DialogTitle    — h2 title
 *   DialogDescription — muted description text
 *   DialogFooter   — action row
 *   DialogClose    — close button / trigger
 */

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialogContext(): DialogContextValue {
  const ctx = React.useContext(DialogContext);
  if (!ctx) {
    throw new Error("Dialog sub-components must be used inside <Dialog>");
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Dialog (root)
// ---------------------------------------------------------------------------

export interface DialogProps {
  /** Controlled open state */
  open?: boolean;
  /** Called when the dialog should open or close */
  onOpenChange?: (open: boolean) => void;
  /** Default open state (uncontrolled) */
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function Dialog({
  open: controlledOpen,
  onOpenChange,
  defaultOpen = false,
  children,
}: DialogProps) {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen);

  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const setOpen = React.useCallback(
    (value: boolean) => {
      if (!isControlled) setInternalOpen(value);
      onOpenChange?.(value);
    },
    [isControlled, onOpenChange],
  );

  return (
    <DialogContext.Provider value={{ open, setOpen }}>
      {children}
    </DialogContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// DialogTrigger
// ---------------------------------------------------------------------------

export interface DialogTriggerProps {
  children: React.ReactElement;
  /** If true, clicking will close instead of open */
  asClose?: boolean;
}

function DialogTrigger({ children, asClose = false }: DialogTriggerProps) {
  const { setOpen } = useDialogContext();

  // React 19 types props as `unknown` on ReactElement; cast to access onClick.
  const childProps = children.props as Record<string, unknown>;
  const childOnClick = childProps["onClick"] as
    | ((e: React.MouseEvent) => void)
    | undefined;

  return React.cloneElement(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    children as React.ReactElement<any>,
    {
      onClick: (e: React.MouseEvent) => {
        childOnClick?.(e);
        setOpen(!asClose);
      },
    },
  );
}

// ---------------------------------------------------------------------------
// DialogContent (the actual panel + portal-like render)
// ---------------------------------------------------------------------------

export interface DialogContentProps {
  className?: string;
  /** Max width of panel. Defaults to "max-w-lg". */
  maxWidth?: string;
  /** Whether clicking the overlay closes the dialog */
  closeOnOverlayClick?: boolean;
  /** Whether pressing Escape closes the dialog */
  closeOnEscape?: boolean;
  children: React.ReactNode;
}

function DialogContent({
  className,
  maxWidth = "max-w-lg",
  closeOnOverlayClick = true,
  closeOnEscape = true,
  children,
}: DialogContentProps) {
  const { open, setOpen } = useDialogContext();

  // Close on Escape key
  React.useEffect(() => {
    if (!closeOnEscape || !open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, closeOnEscape, setOpen]);

  // Lock body scroll while open
  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    /* Overlay */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(30, 41, 59, 0.35)", backdropFilter: "blur(4px)" }}
      role="presentation"
      onClick={closeOnOverlayClick ? () => setOpen(false) : undefined}
    >
      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          // Neuromorphic outset panel — larger shadow than regular cards
          "bg-[#f5f7fa]",
          "[box-shadow:24px_24px_48px_rgba(174,185,201,0.4),-24px_-24px_48px_rgba(255,255,255,0.9)]",
          "rounded-[32px]",
          // Layout
          "w-full relative",
          maxWidth,
          "max-h-[90vh] overflow-y-auto",
          // Animation
          "animate-[fadeIn_0.2s_ease-out_both]",
          className,
        )}
        style={{
          animation: "dialogFadeIn 0.2s ease-out both",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>

      {/* Inline keyframe for dialog animation */}
      <style>{`
        @keyframes dialogFadeIn {
          from { opacity: 0; transform: translateY(12px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DialogHeader
// ---------------------------------------------------------------------------

function DialogHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 px-8 pt-8 pb-6",
        "border-b border-[rgba(174,185,201,0.25)]",
        className,
      )}
    >
      <div className="flex-1 min-w-0">{children}</div>
      <DialogClose aria-label="Close dialog" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// DialogTitle
// ---------------------------------------------------------------------------

function DialogTitle({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        "text-xl font-extrabold text-[#1e293b] tracking-tight",
        className,
      )}
      {...props}
    >
      {children}
    </h2>
  );
}

// ---------------------------------------------------------------------------
// DialogDescription
// ---------------------------------------------------------------------------

function DialogDescription({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("mt-1.5 text-sm text-[#64748b] font-medium leading-relaxed", className)}
      {...props}
    >
      {children}
    </p>
  );
}

// ---------------------------------------------------------------------------
// DialogBody — scrollable content area
// ---------------------------------------------------------------------------

function DialogBody({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-8 py-6", className)} {...props}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DialogFooter
// ---------------------------------------------------------------------------

function DialogFooter({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse sm:flex-row sm:justify-end gap-3 px-8 pb-8 pt-6",
        "border-t border-[rgba(174,185,201,0.25)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DialogClose — X button
// ---------------------------------------------------------------------------

interface DialogCloseProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

function DialogClose({ className, children, ...props }: DialogCloseProps) {
  const { setOpen } = useDialogContext();

  // When children is a ReactElement (e.g. <Button>), clone it with onClick
  // injected rather than wrapping in another <button> (prevents nesting).
  if (children && React.isValidElement(children)) {
    const childProps = (children as React.ReactElement).props as Record<string, unknown>;
    const childOnClick = childProps["onClick"] as
      | ((e: React.MouseEvent) => void)
      | undefined;
    return React.cloneElement(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      children as React.ReactElement<any>,
      {
        onClick: (e: React.MouseEvent) => {
          childOnClick?.(e);
          setOpen(false);
        },
      },
    );
  }

  if (children) {
    return (
      <button
        type="button"
        onClick={() => setOpen(false)}
        className={cn(
          "inline-flex items-center justify-center",
          "transition-all duration-150 ease-out",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3b82f6] focus-visible:ring-offset-2",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  }

  // Default X button
  return (
    <button
      type="button"
      aria-label={props["aria-label"] ?? "Close"}
      onClick={() => setOpen(false)}
      className={cn(
        "flex items-center justify-center w-9 h-9 rounded-2xl shrink-0",
        "text-[#94a3b8]",
        // nm-btn shadow on the close button
        "bg-[#f5f7fa]",
        "[box-shadow:3px_3px_6px_rgba(174,185,201,0.4),-3px_-3px_6px_rgba(255,255,255,0.9)]",
        "hover:text-[#1e293b]",
        "hover:[box-shadow:1.5px_1.5px_3px_rgba(174,185,201,0.4),-1.5px_-1.5px_3px_rgba(255,255,255,0.9)]",
        "hover:translate-y-[1px]",
        "active:[box-shadow:inset_2px_2px_4px_rgba(174,185,201,0.4),inset_-2px_-2px_4px_rgba(255,255,255,0.9)]",
        "active:translate-y-0",
        "transition-all duration-150 ease-out",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3b82f6] focus-visible:ring-offset-1",
        className,
      )}
      {...props}
    >
      <X className="w-4 h-4" />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Confirmation Dialog helper
// ---------------------------------------------------------------------------

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  /** Use "danger" variant for destructive actions */
  variant?: "default" | "danger";
  loading?: boolean;
}

function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  variant = "default",
  loading = false,
}: ConfirmDialogProps) {
  // Inline button styles to avoid circular import
  const primaryClass =
    variant === "danger"
      ? "bg-[#ef4444] text-white [box-shadow:0_0_20px_rgba(239,68,68,0.3),4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)] hover:translate-y-[1px]"
      : "bg-[#3b82f6] text-white [box-shadow:0_0_25px_rgba(59,130,246,0.4),4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)] hover:translate-y-[1px]";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent maxWidth="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className={cn(
              "inline-flex items-center justify-center px-5 py-2.5 rounded-2xl",
              "text-sm font-semibold text-[#1e293b] bg-[#f5f7fa]",
              "[box-shadow:4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)]",
              "hover:translate-y-[1px] hover:[box-shadow:2px_2px_4px_rgba(174,185,201,0.4),-2px_-2px_4px_rgba(255,255,255,0.9)]",
              "transition-all duration-150",
            )}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={cn(
              "inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-2xl",
              "text-sm font-semibold",
              primaryClass,
              "transition-all duration-150",
              "disabled:opacity-45 disabled:cursor-not-allowed",
            )}
          >
            {loading && (
              <span className="inline-block w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
            )}
            {confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export {
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
};
