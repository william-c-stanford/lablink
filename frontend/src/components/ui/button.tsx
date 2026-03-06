/**
 * Button — Neuromorphic button primitive
 *
 * Shadow depth states (from LandingPage.html design system):
 *   default  → nm-btn  (raised, 4px shadow)
 *   hover    → 2px shadow + 1px translateY
 *   active   → nm-btn-active (fully inset)
 *   disabled → 45% opacity, no shadow changes
 *
 * Variants:
 *   primary  → solid #3b82f6 background + blue glow
 *   secondary → nm surface (grey clay) background
 *   ghost    → no background, subtle hover
 *   danger   → red accent
 *   outline  → nm-inset (recessed)
 */

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn, focusRing } from "@/lib/utils";

// ---------------------------------------------------------------------------
// CVA variant definitions
// ---------------------------------------------------------------------------

const buttonVariants = cva(
  // Base classes applied to all variants
  [
    "inline-flex items-center justify-center gap-2",
    "font-semibold tracking-tight",
    "transition-all duration-150 ease-out",
    "cursor-pointer select-none",
    "border-0",
    focusRing,
    // Disabled state
    "disabled:opacity-45 disabled:cursor-not-allowed disabled:transform-none",
  ],
  {
    variants: {
      /** Visual style of the button */
      variant: {
        /**
         * primary — blue fill + nm-glow-blue shadow
         * Mimics LandingPage.html CTA buttons: bg-[#3b82f6] nm-glow-blue
         */
        primary: [
          "bg-[#3b82f6] text-white",
          // Default: blue glow with outset shadow
          "[box-shadow:0_0_25px_rgba(59,130,246,0.4),4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)]",
          // Hover: stronger glow, slight downward shift
          "hover:not-disabled:[box-shadow:0_0_40px_rgba(59,130,246,0.6),2px_2px_4px_rgba(174,185,201,0.4),-2px_-2px_4px_rgba(255,255,255,0.9)] hover:not-disabled:translate-y-[1px]",
          // Active: fully pressed
          "active:[box-shadow:inset_2px_2px_4px_rgba(174,185,201,0.5),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] active:translate-y-0",
          "disabled:[box-shadow:2px_2px_5px_rgba(174,185,201,0.4),-2px_-2px_5px_rgba(255,255,255,0.9)]",
        ],

        /**
         * secondary — grey surface (the "clay") with nm-btn shadow
         * Mimics LandingPage.html .nm-btn class
         */
        secondary: [
          "bg-[#f5f7fa] text-[#1e293b]",
          "[box-shadow:4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)]",
          "hover:not-disabled:[box-shadow:2px_2px_4px_rgba(174,185,201,0.4),-2px_-2px_4px_rgba(255,255,255,0.9)] hover:not-disabled:translate-y-[1px]",
          "active:[box-shadow:inset_2px_2px_4px_rgba(174,185,201,0.4),inset_-2px_-2px_4px_rgba(255,255,255,0.9)] active:translate-y-0",
        ],

        /**
         * ghost — transparent, very subtle hover
         */
        ghost: [
          "bg-transparent text-[#64748b]",
          "[box-shadow:none]",
          "hover:not-disabled:bg-[rgba(174,185,201,0.12)] hover:not-disabled:text-[#1e293b]",
          "active:bg-[rgba(174,185,201,0.2)]",
        ],

        /**
         * danger — red accent for destructive actions
         */
        danger: [
          "bg-[#ef4444] text-white",
          "[box-shadow:0_0_20px_rgba(239,68,68,0.3),4px_4px_8px_rgba(174,185,201,0.4),-4px_-4px_8px_rgba(255,255,255,0.9)]",
          "hover:not-disabled:[box-shadow:0_0_32px_rgba(239,68,68,0.5),2px_2px_4px_rgba(174,185,201,0.4),-2px_-2px_4px_rgba(255,255,255,0.9)] hover:not-disabled:translate-y-[1px]",
          "active:[box-shadow:inset_2px_2px_4px_rgba(174,185,201,0.5),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] active:translate-y-0",
        ],

        /**
         * outline — nm-inset (recessed / sunken) — used for secondary actions
         * where we want to show the button is "already pressed"
         */
        outline: [
          "bg-[#f5f7fa] text-[#3b82f6]",
          "[box-shadow:inset_3px_3px_6px_rgba(174,185,201,0.4),inset_-3px_-3px_6px_rgba(255,255,255,0.9)]",
          "hover:not-disabled:[box-shadow:inset_1px_1px_3px_rgba(174,185,201,0.3),inset_-1px_-1px_3px_rgba(255,255,255,0.7)] hover:not-disabled:text-[#2563eb]",
          "active:[box-shadow:inset_4px_4px_8px_rgba(174,185,201,0.5),inset_-4px_-4px_8px_rgba(255,255,255,0.9)]",
        ],
      },

      /** Size scale */
      size: {
        xs: "text-xs px-3 py-1.5 rounded-xl",
        sm: "text-sm px-4 py-2 rounded-[14px]",
        md: "text-sm px-5 py-2.5 rounded-2xl",
        lg: "text-base px-7 py-3.5 rounded-[20px]",
        xl: "text-lg px-10 py-5 rounded-[24px]",
        icon: "p-2.5 rounded-2xl",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

// ---------------------------------------------------------------------------
// Component types
// ---------------------------------------------------------------------------

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Show a spinner and make non-interactive while true */
  loading?: boolean;
  /** Icon rendered before children */
  leftIcon?: React.ReactNode;
  /** Icon rendered after children */
  rightIcon?: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      loading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      >
        {/* Loading spinner */}
        {loading && (
          <span
            aria-hidden="true"
            className="inline-block w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin"
          />
        )}

        {/* Left icon (hidden during loading) */}
        {!loading && leftIcon && (
          <span className="shrink-0" aria-hidden="true">
            {leftIcon}
          </span>
        )}

        {/* Label */}
        {children}

        {/* Right icon */}
        {!loading && rightIcon && (
          <span className="shrink-0" aria-hidden="true">
            {rightIcon}
          </span>
        )}
      </button>
    );
  },
);

Button.displayName = "Button";

export { Button, buttonVariants };
