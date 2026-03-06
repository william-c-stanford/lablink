/**
 * Input — Neuromorphic text input primitive
 *
 * Shadow depth states:
 *   default  → nm-inset CSS class (sunken / recessed, indicates an editable field)
 *   focus    → deeper inset via CSS :focus selector + blue outline ring
 *   error    → red ring + lighter inset
 *   disabled → reduced opacity, cursor not-allowed
 *
 * Uses the `nm-inset` utility class from index.css so that:
 *   1. Shadow is defined in one place (CSS variable system)
 *   2. tailwind-merge does NOT strip the class (it's not an arbitrary value)
 *   3. The focus deepening is handled by CSS `:focus` via `nm-input-focus` helper
 *
 * Also exports:
 *   Textarea  — multi-line variant
 *   InputGroup — wraps a label + input + helper/error text
 */

import * as React from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Show red styling and aria-invalid */
  error?: boolean;
  /** Icon rendered inside the input on the left */
  leftIcon?: React.ReactNode;
  /** Icon or element rendered inside the input on the right */
  rightIcon?: React.ReactNode;
  /** Wrapper className (wraps leftIcon + input + rightIcon) */
  wrapperClassName?: string;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      wrapperClassName,
      type = "text",
      error = false,
      leftIcon,
      rightIcon,
      disabled,
      ...props
    },
    ref,
  ) => {
    const hasWrapper = Boolean(leftIcon || rightIcon);

    const inputEl = (
      <input
        ref={ref}
        type={type}
        disabled={disabled}
        aria-invalid={error || undefined}
        className={cn(
          // Layout & typography
          "w-full bg-[#f5f7fa] text-[#1e293b]",
          "text-sm font-medium",
          "placeholder:text-[#94a3b8] placeholder:font-normal",
          // Neuromorphic inset — CSS class from index.css
          // (not arbitrary Tailwind to avoid tailwind-merge dedup)
          "nm-inset",
          "rounded-2xl",
          // Spacing — adjust if icons present
          leftIcon ? "pl-10 pr-4 py-3" : "px-4 py-3",
          rightIcon ? "pr-10" : "",
          !leftIcon && !rightIcon ? "px-4 py-3" : "",
          // Transitions
          "transition-all duration-150 ease-out",
          // Focus: blue outline ring (shadow deepens via nm-input CSS class)
          "focus:outline-none focus:[outline:2px_solid_#3b82f6] focus:[outline-offset:2px]",
          // Error state: red outline ring
          error && "[outline:2px_solid_#ef4444] [outline-offset:2px]",
          // Disabled
          "disabled:opacity-45 disabled:cursor-not-allowed",
          // Remove browser default styles
          "appearance-none border-0",
          className,
        )}
        {...props}
      />
    );

    if (!hasWrapper) return inputEl;

    return (
      <div className={cn("relative flex items-center", wrapperClassName)}>
        {leftIcon && (
          <span
            className="absolute left-3.5 text-[#94a3b8] pointer-events-none"
            aria-hidden="true"
          >
            {leftIcon}
          </span>
        )}
        {inputEl}
        {rightIcon && (
          <span
            className="absolute right-3.5 text-[#94a3b8]"
            aria-hidden="true"
          >
            {rightIcon}
          </span>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";

// ---------------------------------------------------------------------------
// Textarea
// ---------------------------------------------------------------------------

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error = false, disabled, ...props }, ref) => (
    <textarea
      ref={ref}
      disabled={disabled}
      aria-invalid={error || undefined}
      className={cn(
        "w-full bg-[#f5f7fa] text-[#1e293b]",
        "text-sm font-medium",
        "placeholder:text-[#94a3b8] placeholder:font-normal",
        // Neuromorphic inset — CSS class from index.css
        "nm-inset",
        "rounded-2xl px-4 py-3",
        "transition-all duration-150 ease-out",
        "focus:outline-none focus:[outline:2px_solid_#3b82f6] focus:[outline-offset:2px]",
        error && "[outline:2px_solid_#ef4444] [outline-offset:2px]",
        "disabled:opacity-45 disabled:cursor-not-allowed",
        "resize-y min-h-[96px]",
        "appearance-none border-0",
        className,
      )}
      {...props}
    />
  ),
);

Textarea.displayName = "Textarea";

// ---------------------------------------------------------------------------
// InputGroup — label + input + helper/error text composition
// ---------------------------------------------------------------------------

export interface InputGroupProps {
  /** <label> text */
  label?: string;
  /** ID connecting label and input */
  htmlFor?: string;
  /** Helper text shown below input */
  helperText?: string;
  /** Error message — replaces helperText and applies error styling */
  errorMessage?: string;
  /** Required indicator */
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}

function InputGroup({
  label,
  htmlFor,
  helperText,
  errorMessage,
  required = false,
  className,
  children,
}: InputGroupProps) {
  const hasError = Boolean(errorMessage);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {label && (
        <label
          htmlFor={htmlFor}
          className="text-sm font-semibold text-[#1e293b] tracking-tight"
        >
          {label}
          {required && (
            <span className="ml-1 text-[#ef4444]" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}

      {children}

      {(helperText || errorMessage) && (
        <p
          className={cn(
            "text-xs font-medium",
            hasError ? "text-[#ef4444]" : "text-[#94a3b8]",
          )}
          role={hasError ? "alert" : undefined}
        >
          {errorMessage ?? helperText}
        </p>
      )}
    </div>
  );
}

export { Input, Textarea, InputGroup };
