/**
 * Toast — Neuromorphic toast notification component
 *
 * Rendered by ToastProvider using the UIStore toast queue.
 * Each toast uses nm-outset shadow + slideInRight animation.
 *
 * Variants match ToastVariant from uiStore:
 *   success → green left border + icon
 *   error   → red left border + icon
 *   warning → amber left border + icon
 *   info    → blue left border + icon
 */

import * as React from "react";
import { CheckCircle, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore, type Toast as ToastData, type ToastVariant } from "@/store";

// ---------------------------------------------------------------------------
// Individual Toast item
// ---------------------------------------------------------------------------

const VARIANT_STYLES: Record<
  ToastVariant,
  { border: string; icon: React.ReactNode; iconColor: string }
> = {
  success: {
    border: "border-l-[#22c55e]",
    icon: <CheckCircle className="w-5 h-5" />,
    iconColor: "text-[#22c55e]",
  },
  error: {
    border: "border-l-[#ef4444]",
    icon: <XCircle className="w-5 h-5" />,
    iconColor: "text-[#ef4444]",
  },
  warning: {
    border: "border-l-[#f59e0b]",
    icon: <AlertTriangle className="w-5 h-5" />,
    iconColor: "text-[#f59e0b]",
  },
  info: {
    border: "border-l-[#3b82f6]",
    icon: <Info className="w-5 h-5" />,
    iconColor: "text-[#3b82f6]",
  },
};

interface ToastItemProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const style = VARIANT_STYLES[toast.variant];

  // Auto-dismiss timer
  React.useEffect(() => {
    if (toast.duration === 0) return;

    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, toast.duration);

    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, onDismiss]);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        // Layout
        "flex items-start gap-3 p-4 w-80 max-w-full",
        // Neuromorphic outset
        "bg-[#f5f7fa]",
        "[box-shadow:8px_8px_16px_rgba(174,185,201,0.4),-8px_-8px_16px_rgba(255,255,255,0.9)]",
        "rounded-[20px]",
        // Left accent border
        "border-l-4",
        style.border,
        // Entry animation
        "animate-[slideInRight_0.25s_ease-out_both]",
      )}
    >
      {/* Icon */}
      <span className={cn("shrink-0 mt-0.5", style.iconColor)}>
        {style.icon}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-[#1e293b]">{toast.title}</p>
        {toast.description && (
          <p className="text-xs text-[#64748b] font-medium mt-0.5 leading-relaxed">
            {toast.description}
          </p>
        )}
      </div>

      {/* Dismiss button */}
      <button
        type="button"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(toast.id)}
        className={cn(
          "shrink-0 flex items-center justify-center w-6 h-6 rounded-xl",
          "text-[#94a3b8] hover:text-[#1e293b]",
          "bg-[#f5f7fa]",
          "[box-shadow:2px_2px_4px_rgba(174,185,201,0.35),-2px_-2px_4px_rgba(255,255,255,0.85)]",
          "hover:[box-shadow:1px_1px_2px_rgba(174,185,201,0.35),-1px_-1px_2px_rgba(255,255,255,0.85)]",
          "hover:translate-y-[0.5px]",
          "active:[box-shadow:inset_1px_1px_2px_rgba(174,185,201,0.4),inset_-1px_-1px_2px_rgba(255,255,255,0.8)]",
          "transition-all duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3b82f6]",
        )}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToastProvider — renders the toast stack
// ---------------------------------------------------------------------------

function ToastProvider() {
  const toasts = useUIStore((s) => s.toasts);
  const removeToast = useUIStore((s) => s.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-label="Notifications"
      className="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 items-end pointer-events-none"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastItem toast={toast} onDismiss={removeToast} />
        </div>
      ))}
    </div>
  );
}

export { ToastProvider, ToastItem };
