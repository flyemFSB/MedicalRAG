// 统一产品标记：墨色方块 + ScanHeart（外壳 / 运营 / 登录共用）。
import { ScanHeart } from "lucide-react";
import { cn } from "../lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid size-6 shrink-0 place-items-center rounded-md bg-ink text-safety-ink",
        className,
      )}
      aria-hidden
    >
      <ScanHeart className="size-3.5" />
    </span>
  );
}
