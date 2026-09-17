import { createFileRoute, Link, Outlet, redirect, useLocation } from "@tanstack/react-router";
import {
  Activity,
  ArrowRightLeft,
  Database,
  GitBranch,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Settings2,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { meQueryOptions } from "../lib/queries";
import { BrandMark } from "../components/brand-mark";
import { Button } from "../components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "../components/ui/sheet";
import { cn } from "../lib/utils";

export const Route = createFileRoute("/admin")({
  // 鉴权必须在 beforeLoad：子路由 loader 先于组件执行，写在组件里的 <Navigate> 会让
  // 未登录用户先发出 /api/admin/* 请求（401 重试放大），且把网络/5xx 误判为“未登录”。
  // 角色门禁同理：me 契约携带 role，非 operator 一律拒绝进入运营台。
  beforeLoad: async ({ context }) => {
    const me = await context.queryClient.ensureQueryData(meQueryOptions());
    if (me === null) throw redirect({ to: "/login" });
    if (me.role !== "operator") throw redirect({ to: "/" });
  },
  component: AdminLayout,
});

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_GROUPS: Array<{ title: string; items: NavEntry[] }> = [
  {
    title: "运营",
    items: [
      { to: "/admin/dashboard", label: "仪表盘", icon: LayoutDashboard, exact: true },
      { to: "/admin/knowledge", label: "知识库", icon: Database },
      { to: "/admin/ingestion", label: "摄取运行", icon: Upload, exact: true },
      { to: "/admin/intents", label: "意图树", icon: GitBranch, exact: true },
      { to: "/admin/mappings", label: "查询术语映射", icon: ArrowRightLeft, exact: true },
      { to: "/admin/settings", label: "模型设置", icon: Settings2, exact: true },
      { to: "/admin/traces", label: "链路追踪", icon: Activity },
      { to: "/admin/feedback", label: "反馈审核", icon: MessageSquareText, exact: true },
    ],
  },
  {
    title: "治理",
    items: [{ to: "/admin/users", label: "用户与工作区", icon: Users, exact: true }],
  },
];

/** 产品标记见 components/brand-mark.tsx。 */

function AdminLayout() {
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div className="flex min-h-0 flex-1 gap-2.5 overflow-hidden">
      <aside className="hidden w-60 shrink-0 flex-col rounded-2xl border border-border/80 bg-surface/90 shadow-[var(--shadow-island)] overflow-hidden md:flex">
        <div className="flex items-center gap-2.5 border-b border-border/50 px-4 py-3">
          <BrandMark />
          <span className="text-body-sm font-semibold tracking-tight text-ink">运营控制台</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
          <SidebarNav onNavigate={() => undefined} />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col rounded-2xl border border-border/80 bg-surface shadow-[var(--shadow-island)] overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border/50 bg-surface px-4 py-2.5 md:hidden">
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger
              render={
                <Button variant="ghost" size="sm" className="gap-1.5 rounded-lg">
                  <Menu className="size-4" aria-hidden />
                  菜单
                </Button>
              }
            />
            <SheetContent
              side="left"
              className="w-68 gap-0 bg-surface p-0 rounded-r-2xl border-r border-border/80 shadow-[var(--shadow-elevated)]"
            >
              <SheetHeader className="border-b border-border/50 px-4 py-3">
                <div className="flex items-center gap-2">
                  <BrandMark />
                  <SheetTitle className="text-body-sm font-semibold text-ink">
                    运营控制台
                  </SheetTitle>
                </div>
              </SheetHeader>
              <div className="flex-1 overflow-y-auto p-2.5">
                <SidebarNav onNavigate={() => setSheetOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
          <span className="text-body-sm font-medium text-muted-foreground">运营控制台</span>
        </div>
        <section className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl p-4 sm:p-6 lg:p-7">
            <Outlet />
          </div>
        </section>
      </div>
    </div>
  );
}

function SidebarNav({ onNavigate }: { onNavigate: () => void }) {
  return (
    <nav aria-label="运营控制台导航" className="flex flex-col gap-4 px-1">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          <p className="mb-1.5 px-2.5 font-mono text-metadata font-semibold tracking-wider text-muted-foreground uppercase">
            {group.title}
          </p>
          <div className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <NavLinkEntry key={item.to} entry={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function NavLinkEntry({ entry, onNavigate }: { entry: NavEntry; onNavigate: () => void }) {
  const location = useLocation();
  const active = entry.exact
    ? location.pathname === entry.to
    : location.pathname.startsWith(entry.to);
  const Icon = entry.icon;

  return (
    <Link
      to={entry.to}
      onClick={onNavigate}
      className={cn(
        "group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-caption text-body transition-all focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none active:scale-[0.99]",
        "hover:bg-panel/70 hover:text-ink",
        active
          ? "bg-panel font-semibold text-ink shadow-xs ring-1 ring-border/60 hover:bg-panel hover:text-ink"
          : "text-muted-foreground",
      )}
    >
      <Icon
        className={cn(
          "size-4 shrink-0 transition-colors",
          active ? "text-accent-ink" : "text-muted-foreground group-hover:text-ink",
        )}
        aria-hidden
      />
      <span>{entry.label}</span>
    </Link>
  );
}
