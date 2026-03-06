/**
 * Spinner — Neuromorphic loading indicator
 *
 * Uses a circular border spinner that matches the accent blue.
 * Sizes: sm | md | lg
 */

import * as React from "react";
import { cn } from "@/lib/utils";

export interface SpinnerProps extends React.HTMLAttributes<HTMLSpanElement> {
  size?: "sm" | "md" | "lg";
  /** Colour of the spinning arc. Defaults to blue accent. */
  color?: "blue" | "white" | "muted";
}

const SIZE_MAP = {
  sm: "w-4 h-4 border-2",
  md: "w-6 h-6 border-2",
  lg: "w-10 h-10 border-[3px]",
};

const COLOR_MAP = {
  blue:  "border-[#3b82f6] border-t-transparent",
  white: "border-white border-t-transparent",
  muted: "border-[#94a3b8] border-t-transparent",
};

function Spinner({ size = "md", color = "blue", className, ...props }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block rounded-full animate-spin",
        SIZE_MAP[size],
        COLOR_MAP[color],
        className,
      )}
      {...props}
    />
  );
}

export { Spinner };
