/**
 * Card — Neuromorphic surface container
 *
 * Two surface variants:
 *   outset  → nm-outset (raised, default)
 *   inset   → nm-inset (recessed, for data display areas)
 *
 * Mirrors LandingPage.html nm-outset / nm-inset panels.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Shadow variant */
  variant?: "outset" | "inset" | "flat";
  /** Hover lift effect (only for outset) */
  hoverable?: boolean;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = "outset", hoverable = false, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "bg-[#f5f7fa] rounded-[32px]",
        // Shadow by variant
        variant === "outset" && [
          "[box-shadow:8px_8px_16px_rgba(174,185,201,0.4),-8px_-8px_16px_rgba(255,255,255,0.9)]",
        ],
        variant === "inset" && [
          "[box-shadow:inset_6px_6px_12px_rgba(174,185,201,0.4),inset_-6px_-6px_12px_rgba(255,255,255,0.9)]",
        ],
        variant === "flat" && ["shadow-none"],
        // Hoverable lift
        hoverable && variant === "outset" && [
          "transition-transform duration-200 ease-out hover:scale-[1.01]",
        ],
        className,
      )}
      {...props}
    />
  ),
);

Card.displayName = "Card";

// ---------------------------------------------------------------------------
// CardHeader
// ---------------------------------------------------------------------------

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex flex-col gap-1.5 px-8 pt-8 pb-4",
      className,
    )}
    {...props}
  />
));

CardHeader.displayName = "CardHeader";

// ---------------------------------------------------------------------------
// CardTitle
// ---------------------------------------------------------------------------

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, children, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("text-lg font-bold text-[#1e293b] tracking-tight", className)}
    {...props}
  >
    {children}
  </h3>
));

CardTitle.displayName = "CardTitle";

// ---------------------------------------------------------------------------
// CardDescription
// ---------------------------------------------------------------------------

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-[#64748b] font-medium leading-relaxed", className)}
    {...props}
  />
));

CardDescription.displayName = "CardDescription";

// ---------------------------------------------------------------------------
// CardContent
// ---------------------------------------------------------------------------

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("px-8 py-4", className)}
    {...props}
  />
));

CardContent.displayName = "CardContent";

// ---------------------------------------------------------------------------
// CardFooter
// ---------------------------------------------------------------------------

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex items-center gap-3 px-8 py-6",
      "border-t border-[rgba(174,185,201,0.2)]",
      className,
    )}
    {...props}
  />
));

CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter };

// ---------------------------------------------------------------------------
// StatCard — metric dashboard widget
// ---------------------------------------------------------------------------

export interface StatCardProps {
  /** Metric label shown below the value */
  label: string;
  /** Primary value displayed large */
  value: React.ReactNode;
  /** Icon element (e.g. <Upload size={22} />) */
  icon?: React.ReactNode;
  /** Icon colour applied to the icon element */
  iconColor?: string;
  /** Delta text (e.g. "+12%", "↑ 5") */
  delta?: string;
  /** Delta colour variant */
  deltaVariant?: "positive" | "negative" | "neutral";
  /** Additional className */
  className?: string;
  /** Click handler — makes the card interactive */
  onClick?: () => void;
}

const DELTA_COLORS = {
  positive: "#22c55e",
  negative: "#ef4444",
  neutral: "#94a3b8",
} as const;

/**
 * StatCard — compact metric widget used in Dashboard overview row.
 *
 * Neuromorphic design:
 *   - Outer shell:  nm-outset (raised card — 8px shadow offsets)
 *   - Icon well:    nm-inset  (recessed icon area — 4px inset offsets)
 *   - Delta badge:  nm-inset-xs (small recessed pill)
 */
function StatCard({
  label,
  value,
  icon,
  iconColor = "#3b82f6",
  delta,
  deltaVariant = "neutral",
  className,
  onClick,
}: StatCardProps) {
  const Tag = onClick ? "button" : ("div" as React.ElementType);

  return (
    <Tag
      className={cn(
        "w-full text-left transition-all duration-200",
        onClick && "cursor-pointer hover:scale-[1.01] active:scale-[0.99]",
        className,
      )}
      style={{
        backgroundColor: "#f5f7fa",
        boxShadow:
          "8px 8px 16px rgba(174,185,201,0.4),-8px -8px 16px rgba(255,255,255,0.9)",
        borderRadius: "1.5rem",
        padding: "1.5rem",
      }}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Icon well */}
        {icon && (
          <div
            className="flex-shrink-0 w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{
              backgroundColor: "#f5f7fa",
              boxShadow:
                "inset 4px 4px 8px rgba(174,185,201,0.4),inset -4px -4px 8px rgba(255,255,255,0.9)",
              color: iconColor,
            }}
          >
            {icon}
          </div>
        )}

        {/* Value + label */}
        <div className="flex-1 min-w-0">
          <div
            className="text-3xl font-extrabold tracking-tighter leading-none"
            style={{ color: "#1e293b" }}
          >
            {value}
          </div>
          <div
            className="text-xs font-bold uppercase tracking-widest mt-1.5"
            style={{ color: "#94a3b8" }}
          >
            {label}
          </div>
        </div>

        {/* Delta badge */}
        {delta && (
          <div
            className="flex-shrink-0 text-xs font-bold px-2 py-1 rounded-full"
            style={{
              backgroundColor: "#f5f7fa",
              boxShadow:
                "inset 2px 2px 4px rgba(174,185,201,0.4),inset -2px -2px 4px rgba(255,255,255,0.9)",
              color: DELTA_COLORS[deltaVariant],
            }}
          >
            {delta}
          </div>
        )}
      </div>
    </Tag>
  );
}

StatCard.displayName = "StatCard";

export { StatCard };
