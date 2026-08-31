import { createFileRoute, Link, Navigate, Outlet, useLocation } from "@tanstack/react-router";
import {
  Activity,
  ArrowRightLeft,
  Database,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  Menu,
  MessageSquareText,
  ScanHeart,
  ScrollText,
  Settings2,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useCurrentUser } from "../lib/queries";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "../components/ui/sheet";
import { cn } from "../lib/utils";

export const Route = createFileRoute("/admin")({
  component: AdminLayout,
});

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_GROUPS: Array<{ title: string; items: NavEntry[] }> = [  {
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
    items: [
      { to: "/admin/users", label: "用户与工作区", icon: Users, exact: true },
      { to: "/admin/audit", label: "审计日志", icon: ScrollText, exact: true },
      { to: "/admin/sample-questions", label: "样例问题", icon: ListChecks, exact: true },
    ],
  },
];

/** 产品标记：accent 圆角方块 + 白 glyph（与根外壳同构）。 */
function BrandMark() {
  return (
    <span className="grid size-6 shrink-0 place-items-center rounded-[6px] bg-primary text-primary-foreground" aria-hidden>
      <ScanHeart className="size-4" />
    </span>
  );
}

function AdminLayout() {
  const { isAuthenticated, isPending } = useCurrentUser();
  const [sheetOpen, setSheetOpen] = useState(false);

  if (isPending) {
    return (
      <div className="flex-1 p-6" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-4 h-64 w-full" />
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-background md:flex">
        <div className="flex items-center gap-2 px-4 pt-4 pb-2">
          <BrandMark />
          <span className="text-subheading font-semibold text-ink">运营控制台</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          <SidebarNav onNavigate={() => undefined} />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border bg-background px-4 py-2 md:hidden">
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-1.5">
                <Menu className="size-4" aria-hidden />
                菜单
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="gap-0 bg-panel p-0">
              <SheetHeader className="border-b border-border px-4 py-3">
                <div className="flex items-center gap-2">
                  <BrandMark />
                  <SheetTitle className="text-body-sm font-semibold text-ink">运营控制台</SheetTitle>
                </div>
              </SheetHeader>
              <div className="flex-1 overflow-y-auto p-3">
                <SidebarNav onNavigate={() => setSheetOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
          <span className="text-body-sm text-muted-foreground">运营控制台</span>
        </div>
        <section className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
            <Outlet />
          </div>
        </section>
      </div>
    </div>
  );
}

function SidebarNav({ onNavigate }: { onNavigate: () => void }) {
  return (
    <nav aria-label="运营控制台导航" className="flex flex-col gap-5 px-3">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          <p className="mb-1 px-2 text-caption font-semibold tracking-wide text-muted-foreground uppercase">
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
  const active = entry.exact ? location.pathname === entry.to : location.pathname.startsWith(entry.to);
  const Icon = entry.icon;

  return (
    <Link
      to={entry.to}
      onClick={onNavigate}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-body-sm text-body transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        "hover:bg-panel/60 hover:text-ink",
        active && "bg-panel font-medium text-ink hover:bg-panel hover:text-ink",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      {entry.label}
    </Link>
  );
}
