/**
 * Select — Neuromorphic select / dropdown primitive
 *
 * Shadow depth states:
 *   default  → nm-inset (sunken, indicates editable)
 *   focus    → deeper inset + blue ring
 *   open     → dropdown panel appears as nm-outset (raised)
 *   error    → red ring
 *   disabled → 45% opacity
 *
 * Two implementations exported:
 *   NativeSelect  — wraps <select> for maximum compatibility
 *   Select        — alias for NativeSelect (primary export)
 */

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// NativeSelect (wraps <select>) — accessible, works everywhere
// ---------------------------------------------------------------------------

export interface NativeSelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  error?: boolean;
  placeholder?: string;
  /** Icon on left side */
  leftIcon?: React.ReactNode;
  wrapperClassName?: string;
}

const NativeSelect = React.forwardRef<HTMLSelectElement, NativeSelectProps>(
  (
    {
      className,
      wrapperClassName,
      error = false,
      placeholder,
      leftIcon,
      disabled,
      children,
      ...props
    },
    ref,
  ) => (
    <div className={cn("relative flex items-center", wrapperClassName)}>
      {/* Left icon */}
      {leftIcon && (
        <span
          className="absolute left-3.5 text-[#94a3b8] pointer-events-none z-10"
          aria-hidden="true"
        >
          {leftIcon}
        </span>
      )}

      {/* Select element */}
      <select
        ref={ref}
        disabled={disabled}
        aria-invalid={error || undefined}
        className={cn(
          // Layout & appearance
          "w-full appearance-none bg-[#f5f7fa] text-[#1e293b]",
          "text-sm font-medium",
          // Padding — leave room for icons
          leftIcon ? "pl-10" : "pl-4",
          "pr-10 py-3",
          // Neuromorphic inset (same as Input)
          "[box-shadow:inset_6px_6px_12px_rgba(174,185,201,0.4),inset_-6px_-6px_12px_rgba(255,255,255,0.9)]",
          "rounded-2xl",
          // Transitions & focus
          "transition-all duration-150 ease-out",
          "focus:outline-none",
          "[&:focus]:[box-shadow:inset_7px_7px_14px_rgba(174,185,201,0.45),inset_-7px_-7px_14px_rgba(255,255,255,0.95)]",
          "focus:[outline:2px_solid_#3b82f6] focus:[outline-offset:2px]",
          // Error
          error && "[outline:2px_solid_#ef4444] [outline-offset:2px]",
          // Disabled
          "disabled:opacity-45 disabled:cursor-not-allowed",
          // Remove browser default border
          "border-0",
          // Placeholder colour (first option)
          "[&>option:first-child]:text-[#94a3b8]",
          className,
        )}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {children}
      </select>

      {/* Caret icon */}
      <ChevronDown
        className="absolute right-3.5 w-4 h-4 text-[#94a3b8] pointer-events-none"
        aria-hidden="true"
      />
    </div>
  ),
);

NativeSelect.displayName = "NativeSelect";

// Primary alias
const Select = NativeSelect;

// ---------------------------------------------------------------------------
// SelectOption — thin wrapper for <option>
// ---------------------------------------------------------------------------

export interface SelectOptionProps
  extends React.OptionHTMLAttributes<HTMLOptionElement> {
  children: React.ReactNode;
}

function SelectOption({ children, ...props }: SelectOptionProps) {
  return <option {...props}>{children}</option>;
}

// ---------------------------------------------------------------------------
// SelectGroup — thin wrapper for <optgroup>
// ---------------------------------------------------------------------------

export interface SelectGroupProps
  extends React.OptgroupHTMLAttributes<HTMLOptGroupElement> {
  children: React.ReactNode;
}

function SelectGroup({ children, ...props }: SelectGroupProps) {
  return <optgroup {...props}>{children}</optgroup>;
}

export { Select, NativeSelect, SelectOption, SelectGroup };
