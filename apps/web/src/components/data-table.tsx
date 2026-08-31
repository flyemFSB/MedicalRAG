import {
  type ColumnDef,
  type RowData,
  type SortingState,
  flexRender,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { appTableFeatures, type AppTableFeatures } from "@/lib/table";

/* 统一数据表（shadcn Data Table 配方：TanStack Table + shadcn Table）。
   支持排序、加载骨架、教学式空态、行内操作列。
   v9：features 集统一来自 lib/table（仅排序），列类型携带 AppTableFeatures。 */

interface DataTableProps<TData extends RowData> {
  columns: ColumnDef<AppTableFeatures, TData>[];
  data: TData[];
  ariaLabel: string;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  /** 行内操作列（右对齐；有值时自动追加「操作」列头） */
  renderRowActions?: (row: TData) => ReactNode;
  /** 操作列宽度（默认 120px） */
  actionsWidth?: number;
}

export function DataTable<TData extends RowData>({
  columns,
  data,
  ariaLabel,
  loading,
  emptyTitle,
  emptyDescription,
  renderRowActions,
  actionsWidth = 120,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useTable({
    features: appTableFeatures,
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
  });
  const hasActions = renderRowActions != null;
  const colSpan = columns.length + (hasActions ? 1 : 0);

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <Table aria-label={ariaLabel}>
        <TableHeader className="sticky top-0 z-sticky bg-card">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="hover:bg-transparent">
              {headerGroup.headers.map((header) => (
                <TableHead
                  key={header.id}
                  scope="col"
                  aria-sort={
                    header.column.getIsSorted() === "asc"
                      ? "ascending"
                      : header.column.getIsSorted() === "desc"
                        ? "descending"
                        : "none"
                  }
                >
                  {header.isPlaceholder ? null : header.column.getCanSort() ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-sm text-left font-semibold text-inherit outline-none hover:text-accent-ink focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" ? (
                        <ArrowUp className="size-3.5" aria-hidden />
                      ) : header.column.getIsSorted() === "desc" ? (
                        <ArrowDown className="size-3.5" aria-hidden />
                      ) : (
                        <ArrowUpDown className="size-3.5 text-muted-foreground/60" aria-hidden />
                      )}
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </TableHead>
              ))}
              {hasActions ? (
                <TableHead scope="col" className="text-right">
                  <span className="sr-only">操作</span>
                </TableHead>
              ) : null}
            </TableRow>
          ))}
        </TableHeader>
        {loading ? (
          <TableBody>
            {Array.from({ length: 4 }, (_, r) => (
              <TableRow key={r} className="hover:bg-transparent">
                {Array.from({ length: colSpan }, (_, c) => (
                  <TableCell key={c}>
                    <Skeleton className="h-3.5 w-full" />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        ) : data.length === 0 ? (
          <TableBody>
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={colSpan}>
                <EmptyState
                  title={emptyTitle ?? "暂无数据"}
                  description={emptyDescription ?? "内容会显示在这里。"}
                />
              </TableCell>
            </TableRow>
          </TableBody>
        ) : (
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              // v9：getIsSelected 属 rowSelectionFeature（未注册），此处无选择语义。
              <TableRow key={row.id} className="group">
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
                {hasActions ? (
                  <TableCell className={cn("text-right")} style={{ width: actionsWidth }}>
                    <div className="flex justify-end gap-1 hoverable:opacity-0 hoverable:transition-opacity hoverable:group-hover:opacity-100 hoverable:group-focus-within:opacity-100">
                      {renderRowActions?.(row.original)}
                    </div>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>
    </div>
  );
}

function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
      {icon ? (
        <div className="mb-1 grid size-10 place-items-center rounded-full bg-panel text-muted-foreground">
          {icon}
        </div>
      ) : null}
      <p className="text-subheading font-semibold text-ink">{title}</p>
      {description ? <p className="max-w-[42ch] text-body-sm text-muted-foreground">{description}</p> : null}
      {action}
    </div>
  );
}
