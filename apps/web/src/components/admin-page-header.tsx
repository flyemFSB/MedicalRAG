// 管理页头（icon / title / description / actions；14 个 admin 屏共用，去掉页头样板拷贝）。
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function AdminPageHeader({
  icon: Icon,
  title,
  description,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  /** 右侧操作区（可选；无动作时不渲染空容器）。 */
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-border/40 pb-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-3.5">
        <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-panel/80 text-ink shadow-2xs ring-1 ring-border/50">
          <Icon className="size-4 text-ink/80" aria-hidden />
        </span>
        <div className="min-w-0">
          <h1 className="text-heading-lg font-semibold tracking-tight text-ink">{title}</h1>
          <p className="mt-1 max-w-[64ch] text-body-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
      </div>
      {actions != null ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
