/**
 * Badge — Neuromorphic status badge / tag primitive
 *
 * Variants:
 *   default   → grey surface, nm-inset (recessed)
 *   primary   → blue fill
 *   success   → green fill
 *   warning   → amber fill
 *   danger    → red fill
 *   info      → indigo fill
 *   outline   → blue border, transparent fill
 *
 * Status-specific helpers (maps to upload/experiment states):
 *   uploading → info (blue pulse animation)
 *   parsing   → warning (amber pulse)
 *   parsed    → success (green)
 *   failed    → danger (red)
 *   pending   → default (grey)
 *   active    → primary (blue)
 *   completed → success
 *   cancelled → default
 *
 * Sizes: sm | md | lg
 */

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// CVA definition
// ---------------------------------------------------------------------------

const badgeVariants = cva(
  [
    "inline-flex items-center gap-1.5",
    "font-bold uppercase tracking-widest",
    "select-none",
  ],
  {
    variants: {
      variant: {
        /** Neutral grey, recessed — for default/pending/inactive states */
        default: [
          "bg-[#f5f7fa] text-[#64748b]",
          "[box-shadow:inset_3px_3px_6px_rgba(174,185,201,0.35),inset_-3px_-3px_6px_rgba(255,255,255,0.85)]",
        ],

        /** Blue fill — primary action or selected state */
        primary: [
          "bg-[#3b82f6] text-white",
          "[box-shadow:0_0_12px_rgba(59,130,246,0.35),2px_2px_4px_rgba(174,185,201,0.3),-2px_-2px_4px_rgba(255,255,255,0.8)]",
        ],

        /** Green — success, parsed, completed */
        success: [
          "bg-[#22c55e] text-white",
          "[box-shadow:0_0_12px_rgba(34,197,94,0.3),2px_2px_4px_rgba(174,185,201,0.3),-2px_-2px_4px_rgba(255,255,255,0.8)]",
        ],

        /** Amber — warning, parsing in progress */
        warning: [
          "bg-[#f59e0b] text-white",
          "[box-shadow:0_0_12px_rgba(245,158,11,0.3),2px_2px_4px_rgba(174,185,201,0.3),-2px_-2px_4px_rgba(255,255,255,0.8)]",
        ],

        /** Red — danger, failed, error */
        danger: [
          "bg-[#ef4444] text-white",
          "[box-shadow:0_0_12px_rgba(239,68,68,0.3),2px_2px_4px_rgba(174,185,201,0.3),-2px_-2px_4px_rgba(255,255,255,0.8)]",
        ],

        /** Indigo — informational, uploading */
        info: [
          "bg-[#6366f1] text-white",
          "[box-shadow:0_0_12px_rgba(99,102,241,0.3),2px_2px_4px_rgba(174,185,201,0.3),-2px_-2px_4px_rgba(255,255,255,0.8)]",
        ],

        /** Outline — blue border, transparent bg */
        outline: [
          "bg-transparent text-[#3b82f6]",
          "[box-shadow:inset_2px_2px_4px_rgba(174,185,201,0.3),inset_-2px_-2px_4px_rgba(255,255,255,0.8)]",
          "ring-1 ring-[#3b82f6]/40",
        ],
      },

      size: {
        sm: "text-[9px] px-2 py-0.5 rounded-lg",
        md: "text-[10px] px-2.5 py-1 rounded-xl",
        lg: "text-xs px-3 py-1.5 rounded-xl",
      },

      /** Add animated dot before the label */
      pulse: {
        true: "",
        false: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
      pulse: false,
    },
  },
);

// ---------------------------------------------------------------------------
// Component types
// ---------------------------------------------------------------------------

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  /** Icon on left */
  icon?: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, pulse, icon, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ variant, size, pulse }), className)}
      {...props}
    >
      {/* Animated pulse dot */}
      {pulse && (
        <span
          aria-hidden="true"
          className={cn(
            "inline-block w-1.5 h-1.5 rounded-full animate-pulse",
            variant === "info" && "bg-white",
            variant === "warning" && "bg-white",
            variant === "success" && "bg-white",
            variant === "danger" && "bg-white",
            variant === "primary" && "bg-white",
            (!variant || variant === "default") && "bg-[#3b82f6]",
          )}
        />
      )}

      {/* Optional icon */}
      {icon && !pulse && (
        <span aria-hidden="true" className="shrink-0">
          {icon}
        </span>
      )}

      {children}
    </span>
  ),
);

Badge.displayName = "Badge";

// ---------------------------------------------------------------------------
// UploadStatusBadge — convenience component for upload status strings
// ---------------------------------------------------------------------------

export type UploadStatus =
  | "pending"
  | "uploading"
  | "parsing"
  | "parsed"
  | "failed"
  | "queued";

const UPLOAD_STATUS_VARIANT: Record<
  UploadStatus,
  VariantProps<typeof badgeVariants>["variant"]
> = {
  pending:   "default",
  queued:    "default",
  uploading: "info",
  parsing:   "warning",
  parsed:    "success",
  failed:    "danger",
};

const UPLOAD_STATUS_PULSE: Record<UploadStatus, boolean> = {
  pending:   false,
  queued:    false,
  uploading: true,
  parsing:   true,
  parsed:    false,
  failed:    false,
};

const UPLOAD_STATUS_LABEL: Record<UploadStatus, string> = {
  pending:   "Pending",
  queued:    "Queued",
  uploading: "Uploading",
  parsing:   "Parsing",
  parsed:    "Parsed",
  failed:    "Failed",
};

export interface UploadStatusBadgeProps
  extends Omit<BadgeProps, "variant" | "pulse"> {
  status: UploadStatus;
}

function UploadStatusBadge({ status, ...props }: UploadStatusBadgeProps) {
  return (
    <Badge
      variant={UPLOAD_STATUS_VARIANT[status]}
      pulse={UPLOAD_STATUS_PULSE[status]}
      {...props}
    >
      {UPLOAD_STATUS_LABEL[status]}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// ExperimentStatusBadge — for experiment state machine
// ---------------------------------------------------------------------------

export type ExperimentStatus =
  | "draft"
  | "active"
  | "completed"
  | "archived"
  | "cancelled";

const EXPERIMENT_STATUS_VARIANT: Record<
  ExperimentStatus,
  VariantProps<typeof badgeVariants>["variant"]
> = {
  draft:     "default",
  active:    "primary",
  completed: "success",
  archived:  "outline",
  cancelled: "default",
};

const EXPERIMENT_STATUS_LABEL: Record<ExperimentStatus, string> = {
  draft:     "Draft",
  active:    "Active",
  completed: "Completed",
  archived:  "Archived",
  cancelled: "Cancelled",
};

export interface ExperimentStatusBadgeProps
  extends Omit<BadgeProps, "variant" | "pulse"> {
  status: ExperimentStatus;
}

function ExperimentStatusBadge({
  status,
  ...props
}: ExperimentStatusBadgeProps) {
  return (
    <Badge variant={EXPERIMENT_STATUS_VARIANT[status]} {...props}>
      {EXPERIMENT_STATUS_LABEL[status]}
    </Badge>
  );
}

export {
  Badge,
  badgeVariants,
  UploadStatusBadge,
  ExperimentStatusBadge,
};
