import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/* 语义告警（DESIGN §5.3：安全边界等最高信号用 medical 变体，禁用 border-left 强调）。 */
const alertVariants = cva(
  "relative grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 rounded-lg border p-4 text-body-sm",
  {
    variants: {
      variant: {
        default: "border-border bg-card text-body",
        info: "border-info/30 bg-info-soft text-info",
        success: "border-success/30 bg-success-soft text-success",
        warning: "border-warning/30 bg-warning-soft text-warning",
        error: "border-error/30 bg-error-soft text-error",
        medical: "border-medical/40 bg-medical-soft text-medical",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

function AlertTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-title"
      className={cn("col-start-2 font-semibold leading-snug text-ink", className)}
      {...props}
    />
  );
}

function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-description"
      className={cn("col-start-2 text-body-sm leading-relaxed", className)}
      {...props}
    />
  );
}

function AlertIcon({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-icon"
      className={cn("col-start-1 row-span-2 row-start-1 grid size-5 place-items-center", className)}
      {...props}
    />
  );
}

export { Alert, AlertDescription, AlertIcon, AlertTitle, alertVariants };
