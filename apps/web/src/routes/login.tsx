// 登录/注册（shadcn 卡片表单；Query useMutation → 失效 me → 导航回工作台）。
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { ScanHeart } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
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
        setError(err.status === 401 ? "邮箱或密码错误" : err.status === 409 ? "该邮箱已注册" : "请求失败，请稍后重试");
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
    <section className="grid min-h-0 flex-1 gap-3 p-3 sm:p-4 lg:grid-cols-2">
      <div className="hidden flex-col justify-center px-8 py-12 lg:flex">
        <div className="flex items-center gap-2">
          <BrandMark />
          <span className="font-semibold text-ink">MedicalRAG</span>
        </div>
        <h1 className="mt-8 max-w-[14ch] font-sans text-display font-semibold text-balance text-ink">
          每个答案，都有据可查。
        </h1>
        <p className="mt-3 max-w-[40ch] text-body text-muted-foreground">
          面向医疗来源的循证问答：检索你的知识库、标注证据来源，并在涉及治疗、用药或急症时明确安全边界。
        </p>
        <div className="mt-10 w-full max-w-sm rounded-md border border-border bg-panel p-4">
          <div className="flex items-center gap-2">
            <span className="shrink-0 rounded-md bg-accent-soft px-2 py-0.5 text-caption font-semibold text-accent-soft-ink">
              [1]
            </span>
            <span className="min-w-0 flex-1 truncate text-body-sm font-medium text-ink">来源文档标题</span>
            <span className="shrink-0 text-caption font-medium text-muted-foreground tabular-nums">86%</span>
          </div>
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-panel">
            <div className="h-full rounded-full bg-accent-ink" style={{ width: "86%" }} aria-hidden />
          </div>
          <p className="mt-2 text-body-sm leading-relaxed text-body line-clamp-2">
            每个回答都指向可追溯的证据：来源、分块与相关度评分一览可见。
          </p>
        </div>
      </div>
      <div className="flex items-center justify-center p-6">
        <Card className="w-full max-w-sm gap-4">
          <CardHeader>
            <div className="flex items-center gap-2 font-semibold text-ink lg:hidden">
              <BrandMark />
              MedicalRAG
            </div>
            <CardTitle className="text-heading">{mode === "login" ? "登录" : "注册"}</CardTitle>
            <CardDescription>证据优先的医疗知识工作台</CardDescription>
          </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>
            {error ? (
              <Alert variant="error">
                <AlertTitle>无法继续</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit" disabled={mutation.isPending} className="mt-1">
              {mutation.isPending ? "提交中…" : mode === "login" ? "登录" : "注册"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center">
          <button
            type="button"
            onClick={toggleMode}
            className="rounded-sm text-body-sm text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
          >
            {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
          </button>
        </CardFooter>
      </Card>
      </div>
    </section>
  );
}

/** 产品标记：accent 圆角方块 + 白 glyph（与根外壳同构）。 */
function BrandMark() {
  return (
    <span className="grid size-6 shrink-0 place-items-center rounded-[6px] bg-primary text-primary-foreground" aria-hidden>
      <ScanHeart className="size-4" />
    </span>
  );
}
