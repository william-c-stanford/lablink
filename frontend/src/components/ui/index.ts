/**
 * LabLink Neuromorphic UI Component Library
 *
 * All components follow the neuromorphic design system:
 *   - Surface:  #f5f7fa (--bg)
 *   - Accent:   #3b82f6 (--blue)
 *   - Shadow dark:  rgba(174, 185, 201, 0.4)
 *   - Shadow light: rgba(255, 255, 255, 0.9)
 *
 * Shadow depth states:
 *   nm-outset  → raised card/panel
 *   nm-inset   → sunken input/data area
 *   nm-btn     → interactive default
 *   nm-btn:hover → 1px down, softer shadow
 *   nm-btn:active → fully inset
 */

// Button
export { Button, buttonVariants } from "./button";
export type { ButtonProps } from "./button";

// Card
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  StatCard,
} from "./card";
export type { CardProps, StatCardProps } from "./card";

// Badge
export {
  Badge,
  badgeVariants,
  UploadStatusBadge,
  ExperimentStatusBadge,
} from "./badge";
export type {
  BadgeProps,
  UploadStatus,
  ExperimentStatus,
  UploadStatusBadgeProps,
  ExperimentStatusBadgeProps,
} from "./badge";

// Input
export { Input, Textarea, InputGroup } from "./input";
export type { InputProps, TextareaProps, InputGroupProps } from "./input";

// Label
export { Label } from "./label";
export type { LabelProps } from "./label";

// Select
export {
  Select,
  NativeSelect,
  SelectOption,
  SelectGroup,
} from "./select";
export type {
  NativeSelectProps,
  SelectOptionProps,
  SelectGroupProps,
} from "./select";

// Dialog / Modal
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
} from "./dialog";
export type { DialogProps, DialogContentProps, ConfirmDialogProps } from "./dialog";

// Separator
export { Separator } from "./separator";
export type { SeparatorProps } from "./separator";

// Spinner
export { Spinner } from "./spinner";
export type { SpinnerProps } from "./spinner";

// DataTable
export { DataTable } from "./data-table";
export type { DataTableProps, ColumnDef, SortDirection } from "./data-table";

// Toast
export { ToastProvider, ToastItem } from "./toast";

// HighlightedText
export { HighlightedText } from "./HighlightedText";
