/**
 * DataTable -- Neuromorphic sortable data table component.
 *
 * Design:
 *   - Outer shell: nm-outset card with rounded-[32px]
 *   - Header row: bold text with sort indicators, nm-inset-xs bottom border
 *   - Body rows: alternating subtle background tint for readability
 *   - Loading state: skeleton shimmer rows via .animate-shimmer
 *   - Empty state: centered muted message
 *
 * Props:
 *   columns   -- column definitions (key, header label, sortable flag, render fn)
 *   data      -- array of row objects
 *   onSort    -- callback when a sortable column header is clicked
 *   sortKey   -- currently sorted column key
 *   sortDir   -- current sort direction
 *   loading   -- show skeleton loading state
 *   emptyText -- message shown when data is empty
 *   className -- additional className for the outer wrapper
 */

import * as React from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SortDirection = "asc" | "desc";

export interface ColumnDef<T> {
  /** Unique key identifying this column (used for sort callbacks) */
  key: string;
  /** Header label displayed in the table head */
  header: string;
  /** Whether this column is sortable */
  sortable?: boolean;
  /** Custom render function for cell content. Receives the row data. */
  render?: (row: T, rowIndex: number) => React.ReactNode;
  /** Optional className applied to both th and td for this column */
  className?: string;
  /** Column width (CSS value, e.g. "120px", "20%") */
  width?: string;
}

export interface DataTableProps<T> {
  /** Column definitions */
  columns: ColumnDef<T>[];
  /** Row data array */
  data: T[];
  /** Callback when a sortable column header is clicked */
  onSort?: (key: string, direction: SortDirection) => void;
  /** Currently sorted column key */
  sortKey?: string;
  /** Current sort direction */
  sortDir?: SortDirection;
  /** Show skeleton loading state */
  loading?: boolean;
  /** Number of skeleton rows to show while loading */
  skeletonRows?: number;
  /** Message shown when data is empty and not loading */
  emptyText?: string;
  /** Extract a unique key from each row (defaults to index) */
  rowKey?: (row: T, index: number) => string | number;
  /** Optional click handler for rows */
  onRowClick?: (row: T, index: number) => void;
  /** Additional className for the outer wrapper */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function DataTableInner<T>(
  {
    columns,
    data,
    onSort,
    sortKey,
    sortDir,
    loading = false,
    skeletonRows = 5,
    emptyText = "No data available",
    rowKey,
    onRowClick,
    className,
  }: DataTableProps<T>,
  ref: React.ForwardedRef<HTMLDivElement>,
) {
  function handleSort(col: ColumnDef<T>) {
    if (!col.sortable || !onSort) return;

    const newDir: SortDirection =
      sortKey === col.key && sortDir === "asc" ? "desc" : "asc";
    onSort(col.key, newDir);
  }

  function getRowKey(row: T, index: number): string | number {
    if (rowKey) return rowKey(row, index);
    // Attempt to use common id fields
    const r = row as Record<string, unknown>;
    if (typeof r["id"] === "string" || typeof r["id"] === "number") return r["id"] as string | number;
    return index;
  }

  return (
    <div
      ref={ref}
      className={cn(
        // Neuromorphic outset card wrapper
        "bg-[#f5f7fa] rounded-[32px] overflow-hidden",
        "[box-shadow:8px_8px_16px_rgba(174,185,201,0.4),-8px_-8px_16px_rgba(255,255,255,0.9)]",
        className,
      )}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          {/* ── Header ────────────────────────────────────────────────────── */}
          <thead>
            <tr
              style={{
                borderBottom: "1px solid rgba(174, 185, 201, 0.25)",
              }}
            >
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "px-6 py-4 text-left text-xs font-bold uppercase tracking-widest",
                    "text-[#94a3b8] select-none",
                    col.sortable && "cursor-pointer hover:text-[#3b82f6] transition-colors duration-150",
                    col.className,
                  )}
                  style={col.width ? { width: col.width } : undefined}
                  onClick={() => handleSort(col)}
                  aria-sort={
                    sortKey === col.key
                      ? sortDir === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                >
                  <span className="inline-flex items-center gap-1.5">
                    {col.header}
                    {col.sortable && (
                      <SortIcon
                        active={sortKey === col.key}
                        direction={sortKey === col.key ? sortDir : undefined}
                      />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>

          {/* ── Body ──────────────────────────────────────────────────────── */}
          <tbody>
            {loading
              ? /* Skeleton rows */
                Array.from({ length: skeletonRows }).map((_, i) => (
                  <tr key={`skel-${i}`}>
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={cn("px-6 py-4", col.className)}
                      >
                        <div
                          className="h-4 rounded-lg animate-shimmer"
                          style={{ width: `${60 + Math.random() * 30}%` }}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              : data.length === 0
                ? /* Empty state */
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-6 py-16 text-center"
                    >
                      <p
                        className="text-sm font-semibold"
                        style={{ color: "var(--text-subtle)" }}
                      >
                        {emptyText}
                      </p>
                    </td>
                  </tr>
                : /* Data rows */
                  data.map((row, rowIndex) => (
                    <tr
                      key={getRowKey(row, rowIndex)}
                      className={cn(
                        "transition-colors duration-100",
                        // Alternating row backgrounds
                        rowIndex % 2 === 1 && "bg-white/30",
                        // Hover
                        "hover:bg-white/50",
                        // Clickable
                        onRowClick && "cursor-pointer",
                        // Row divider
                      )}
                      style={{
                        borderBottom:
                          rowIndex < data.length - 1
                            ? "1px solid rgba(174, 185, 201, 0.15)"
                            : undefined,
                      }}
                      onClick={
                        onRowClick
                          ? () => onRowClick(row, rowIndex)
                          : undefined
                      }
                    >
                      {columns.map((col) => (
                        <td
                          key={col.key}
                          className={cn(
                            "px-6 py-4 text-sm font-medium",
                            "text-[#1e293b]",
                            col.className,
                          )}
                        >
                          {col.render
                            ? col.render(row, rowIndex)
                            : String(
                                (row as Record<string, unknown>)[col.key] ?? "",
                              )}
                        </td>
                      ))}
                    </tr>
                  ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Use a type assertion to preserve generic type parameter through forwardRef
export const DataTable = React.forwardRef(DataTableInner) as <T>(
  props: DataTableProps<T> & { ref?: React.Ref<HTMLDivElement> },
) => React.ReactElement | null;

// ---------------------------------------------------------------------------
// SortIcon
// ---------------------------------------------------------------------------

interface SortIconProps {
  active: boolean;
  direction?: SortDirection;
}

function SortIcon({ active, direction }: SortIconProps) {
  if (!active || !direction) {
    return (
      <ChevronsUpDown
        size={14}
        strokeWidth={2}
        className="text-[#cbd5e1]"
        aria-hidden="true"
      />
    );
  }

  if (direction === "asc") {
    return (
      <ChevronUp
        size={14}
        strokeWidth={2.5}
        className="text-[#3b82f6]"
        aria-hidden="true"
      />
    );
  }

  return (
    <ChevronDown
      size={14}
      strokeWidth={2.5}
      className="text-[#3b82f6]"
      aria-hidden="true"
    />
  );
}
