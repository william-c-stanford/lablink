/**
 * Label — Accessible form label
 *
 * Styled with the neuromorphic typography system (Plus Jakarta Sans, semibold).
 */

import * as React from "react";
import { cn } from "@/lib/utils";

export interface LabelProps
  extends React.LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean;
}

const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, required = false, children, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "text-sm font-semibold text-[#1e293b] tracking-tight",
        "cursor-pointer select-none",
        className,
      )}
      {...props}
    >
      {children}
      {required && (
        <span className="ml-1 text-[#ef4444]" aria-hidden="true">
          *
        </span>
      )}
    </label>
  ),
);

Label.displayName = "Label";

export { Label };
