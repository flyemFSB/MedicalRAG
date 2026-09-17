// 登录/注册（shadcn 卡片表单；Query useMutation → 失效 me → 导航回工作台）。
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { BrandMark } from "../components/brand-mark";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { ApiError, login as loginRequest, register as registerRequest } from "../lib/api";
import { authKeys } from "../lib/queries";

export const Route = createFileRoute("/login")({
  component: LoginScreen,
});

type Mode = "login" | "register";

function LoginScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const body = { email, password };
      return mode === "login" ? loginRequest(body) : registerRequest(body);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: authKeys.all });
      await router.navigate({ to: "/" });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(
          err.status === 401
            ? "邮箱或密码错误"
            : err.status === 409
              ? "该邮箱已注册"
              : "请求失败，请稍后重试",
        );
      } else {
        setError("请求失败，请稍后重试");
      }
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  }

  function toggleMode() {
    setMode(mode === "login" ? "register" : "login");
    setError(null);
  }

  return (
    <section className="mx-auto grid min-h-0 flex-1 w-full max-w-5xl items-center gap-4 p-2 sm:p-4 lg:grid-cols-2">
      <div className="hidden flex-col justify-center rounded-2xl border border-border/80 bg-surface/90 p-8 sm:p-10 shadow-[var(--shadow-island)] lg:flex">
        <div className="flex items-center gap-2">
          <BrandMark />
          <span className="text-body-sm font-semibold text-ink">MedicalRAG</span>
        </div>
        <h1 className="mt-6 max-w-[14ch] font-display text-display font-semibold tracking-tight text-balance text-ink">
          每个答案，都有据可查。
        </h1>
        <p className="mt-3 max-w-[40ch] text-body-sm leading-relaxed text-muted-foreground">
          面向医疗来源的循证问答：检索你的知识库、标注证据来源，并在涉及治疗、用药或急症时明确安全边界。
        </p>
        <div className="mt-8 w-full max-w-sm rounded-xl border border-border/70 bg-panel/40 p-3.5 shadow-2xs">
          <div className="flex items-center gap-2">
            <span className="shrink-0 rounded-md bg-accent-soft px-1.5 py-0.5 text-metadata font-semibold text-accent-soft-ink">
              [1]
            </span>
            <span className="min-w-0 flex-1 truncate text-caption font-semibold text-ink">
              来源文档标题
            </span>
            <span className="shrink-0 text-metadata font-mono font-medium text-muted-foreground tabular-nums">
              86%
            </span>
          </div>
          <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-panel">
            <div
              className="h-full rounded-full bg-accent-ink"
              style={{ width: "86%" }}
              aria-hidden
            />
          </div>
          <p className="mt-2 text-caption leading-relaxed text-body line-clamp-2">
            每个回答都指向可追溯的证据：来源、分块与相关度评分一览可见。
          </p>
        </div>
      </div>
      <div className="flex items-center justify-center p-2 sm:p-6">
        <Card className="w-full max-w-sm rounded-2xl border border-border/80 bg-surface p-6 shadow-[var(--shadow-island)] gap-4">
          <CardHeader className="p-0">
            <div className="flex items-center gap-2 font-semibold text-ink lg:hidden mb-2">
              <BrandMark />
              <span className="text-body-sm font-semibold">MedicalRAG</span>
            </div>
            <CardTitle className="text-heading font-semibold text-ink">
              {mode === "login" ? "登录" : "注册"}
            </CardTitle>
            <CardDescription className="text-body-sm text-muted-foreground">
              证据优先的医疗知识工作台
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
              <div className="grid gap-1.5">
                <Label htmlFor="email" className="text-caption font-medium">
                  邮箱
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="rounded-xl"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="password" className="text-caption font-medium">
                  密码
                </Label>
                <Input
                  id="password"
                  type="password"
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  className="rounded-xl"
                />
              </div>
              {error ? (
                <Alert variant="destructive" className="rounded-xl">
                  <AlertTitle>无法继续</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
              <Button
                type="submit"
                disabled={mutation.isPending}
                className="mt-1 w-full rounded-xl"
              >
                {mutation.isPending ? "提交中…" : mode === "login" ? "登录" : "注册"}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="justify-center border-t-0 p-0 pt-2">
            <button
              type="button"
              onClick={toggleMode}
              className="rounded-lg text-caption text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            >
              {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
            </button>
          </CardFooter>
        </Card>
      </div>
    </section>
  );
}

/** 产品标记见 components/brand-mark.tsx。 */
