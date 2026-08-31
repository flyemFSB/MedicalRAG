import { createRootRouteWithContext, Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { LogOut, ScanHeart } from "lucide-react";
import { useCurrentUser } from "../lib/queries";
import { authKeys } from "../lib/queries";
import { logout } from "../lib/api";
import { cn } from "../lib/utils";
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
});

function AppShell() {
  return (
    <TooltipProvider>
      <div className="relative flex min-h-svh flex-col bg-canvas text-ink">
        <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-accent-ink">
          跳转到内容
        </a>
        <Topbar />
        <main id="main-content" className="relative flex min-h-0 flex-1 flex-col outline-none" tabIndex={-1}>
          <Outlet />
        </main>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}

const NAV_LINKS = [
  { to: "/", label: "工作台", exact: true },
  { to: "/status", label: "服务状态", exact: true },
  { to: "/admin", label: "运营控制台", exact: false },
] as const;

/** 产品标记：accent 圆角方块 + 白 glyph（外壳与运营侧栏共用同构）。 */
function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid size-6 shrink-0 place-items-center rounded-[6px] bg-primary text-primary-foreground",
        className,
      )}
      aria-hidden
    >
      <ScanHeart className="size-4" />
    </span>
  );
}

function Topbar() {
  const { user, isPending, isAuthenticated } = useCurrentUser();
  const location = useLocation();

  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border bg-background px-4 sm:px-6">
      <nav aria-label="主导航" className="flex min-w-0 items-center gap-1 sm:gap-2">
        <Link to="/" className="mr-2 flex shrink-0 items-center gap-2 font-semibold text-ink sm:mr-4">
          <BrandMark />
          MedicalRAG
        </Link>
        {NAV_LINKS.map((link) => {
          const active = link.exact ? location.pathname === link.to : location.pathname.startsWith(link.to);
          return (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "rounded-full px-3 py-1.5 text-body-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                active
                  ? "bg-panel text-ink"
                  : "text-muted-foreground hover:bg-panel/70 hover:text-ink",
              )}
            >
              {link.label}
            </Link>
          );
        })}
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
  user: { email: string } | undefined;
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
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-9 gap-2 px-2 text-body-sm text-muted-foreground hover:text-ink">
            <Avatar className="size-7">
              <AvatarFallback className="bg-accent-soft text-accent-soft-ink text-caption">
                {user.email.slice(0, 1).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <span className="hidden max-w-40 truncate sm:inline">{user.email}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
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
      className="rounded-md px-2.5 py-1.5 text-body-sm font-medium text-accent-ink transition-colors hover:bg-panel focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      登录
    </Link>
  );
}
