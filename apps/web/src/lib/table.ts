// 全应用统一 TanStack Table v9 features 集（仅排序；官方 v9 迁移指南：features 显式声明）。
import { createSortedRowModel, rowSortingFeature, tableFeatures } from "@tanstack/react-table";

export const appTableFeatures = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
});

export type AppTableFeatures = typeof appTableFeatures;
