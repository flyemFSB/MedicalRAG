import {
  createRootRouteWithContext,
  Link,
  Outlet,
  useLocation,
  useNavigate,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useCurrentUser } from "../lib/queries";
import { authKeys } from "../lib/queries";
import { logout } from "../lib/api";
import { cn } from "../lib/utils";
import { BrandMark } from "../components/brand-mark";
import { Toaster } from "../components/ui/sonner";
import { TooltipProvider } from "../components/ui/tooltip";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Button } from "../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: AppShell,
  // 渲染期异常兜底（临床级清晰：中文文案 + 单一出路，不落英文默认错误页）
  errorComponent: RouteError,
  notFoundComponent: NotFound,
});

function RouteError({ error, reset }: ErrorComponentProps) {
  const detail = error instanceof Error ? error.message : String(error);
  return (
    <RouteFallback
      title="页面出现异常"
      description="渲染时发生未预期的错误。可尝试重新加载；若持续出现，请通过运营台反馈问题。"
      detail={detail}
      actionLabel="重新加载"
      onAction={reset}
    />
  );
}

function NotFound() {
  return (
    <RouteFallback
      title="页面不存在"
      description="您访问的地址不存在或已被移除。"
      actionLabel="返回工作台"
      onAction={() => {
        window.location.assign("/");
      }}
    />
  );
}

function RouteFallback({
  title,
  description,
  detail,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  detail?: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center p-6">
      <div
        role="alert"
        className="w-full max-w-md rounded-2xl border border-border/80 bg-surface p-6 sm:p-8 text-center shadow-[var(--shadow-island)]"
      >
        <h1 className="font-display text-subheading font-semibold tracking-tight text-ink">
          {title}
        </h1>
        <p className="mt-2 text-body-sm leading-relaxed text-muted-foreground">{description}</p>
        {detail ? (
          <p className="mt-3 truncate font-mono text-caption text-faint" title={detail}>
            {detail}
          </p>
        ) : null}
        <div className="mt-5 flex justify-center">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      </div>
    </div>
  );
}

function AppShell() {
  const location = useLocation();
  const isChat = location.pathname === "/";

  return (
    <TooltipProvider>
      <div
        className={cn(
          "relative flex h-svh flex-col overflow-hidden text-ink",
          isChat ? "bg-surface p-0 gap-0" : "bg-canvas p-2 sm:p-2.5 gap-2 sm:gap-2.5",
        )}
      >
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-accent-ink"
        >
          跳转到内容
        </a>
        <Topbar isChat={isChat} />
        <main
          id="main-content"
          className="relative flex min-h-0 flex-1 flex-col outline-none overflow-hidden"
          tabIndex={-1}
        >
          <Outlet />
        </main>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}

const NAV_LINKS = [
  { to: "/", label: "工作台", exact: true, operatorOnly: false },
  { to: "/status", label: "服务状态", exact: true, operatorOnly: false },
  { to: "/admin", label: "运营控制台", exact: false, operatorOnly: true },
] as const;

/** 产品标记见 components/brand-mark.tsx。 */

function Topbar({ isChat }: { isChat?: boolean }) {
  const { user, isPending, isAuthenticated } = useCurrentUser();
  const location = useLocation();

  return (
    <header
      className={cn(
        "flex h-11 shrink-0 items-center justify-between gap-3 px-3 sm:px-4 backdrop-blur-md",
        isChat
          ? "border-b border-border/70 bg-surface/95"
          : "rounded-2xl border border-border/80 bg-surface/90 shadow-[var(--shadow-island)]",
      )}
    >
      <nav aria-label="主导航" className="flex min-w-0 items-center gap-3 sm:gap-4">
        <Link
          to="/"
          className="flex shrink-0 items-center gap-2 font-semibold text-ink transition-opacity hover:opacity-85"
        >
          <BrandMark />
          <span className="text-body-sm font-semibold tracking-tight text-ink">MedicalRAG</span>
        </Link>
        <div className="flex items-center gap-0.5 rounded-xl bg-panel/75 p-0.5 ring-1 ring-border/40">
          {NAV_LINKS.filter((link) => !link.operatorOnly || user?.role === "operator").map(
            (link) => {
              const active = link.exact
                ? location.pathname === link.to
                : location.pathname.startsWith(link.to);
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={cn(
                    "rounded-lg px-2.5 py-1 text-caption font-medium transition-all focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    active
                      ? "bg-surface font-semibold text-ink shadow-xs ring-1 ring-border/40"
                      : "text-muted-foreground hover:bg-surface/50 hover:text-ink",
                  )}
                >
                  {link.label}
                </Link>
              );
            },
          )}
        </div>
      </nav>
      <AuthStatus isPending={isPending} user={user} isAuthenticated={isAuthenticated} />
    </header>
  );
}

function AuthStatus({
  isPending,
  user,
  isAuthenticated,
}: {
  isPending: boolean;
  user: { email: string } | null | undefined;
  isAuthenticated: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: authKeys.all });
      await navigate({ to: "/login" });
    },
  });

  if (isPending) {
    return <span className="h-4 w-4 animate-pulse rounded-full bg-panel-strong" aria-hidden />;
  }

  if (isAuthenticated && user) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-2 rounded-xl px-2 text-caption text-muted-foreground hover:text-ink"
            >
              <Avatar className="size-6">
                <AvatarFallback className="bg-accent-soft text-accent-soft-ink text-metadata font-semibold">
                  {user.email.slice(0, 1).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <span className="hidden max-w-36 truncate sm:inline">{user.email}</span>
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="w-48 rounded-xl">
          <DropdownMenuLabel className="truncate">{user.email}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
          >
            <LogOut />
            {logoutMutation.isPending ? "退出中…" : "退出登录"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <Link
      to="/login"
      className="rounded-xl border border-border/80 bg-surface px-3 py-1 text-caption font-medium text-ink transition-all hover:bg-panel hover:text-accent-ink focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none active:scale-[0.98]"
    >
      登录
    </Link>
  );
}
