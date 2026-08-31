// 模型设置（CONTEXT.md：模型目标 = 配置的模型提供方与能力集；平台模型凭据 = 操作者管理的秘密）。
import { useQuery } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { Skeleton } from "../../components/ui/skeleton";
import { credentialsQueryOptions, modelTargetsQueryOptions } from "../../lib/queries";
import { formatDateTime } from "../../lib/format";
import { modelTargetTone } from "../../lib/status";

export function SettingsScreen() {
  const { data: targets = [], isPending } = useQuery(modelTargetsQueryOptions());

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <Settings2 className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">模型设置</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">配置模型目标与平台模型凭据；凭据是操作者管理的秘密，不进入工作区数据。</p>
          </div>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>模型目标</CardTitle>
          <p className="text-body-sm text-muted-foreground">生成 / 嵌入 / 重排目标的优先序、能力与熔断状态</p>
        </CardHeader>
        <CardContent>
          <Table aria-label="模型目标列表">
            <TableHeader>
              <TableRow>
                <TableHead>目标</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>模型</TableHead>
                <TableHead>能力</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>熔断</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending
                ? Array.from({ length: 3 }, (_, i) => (
                    <TableRow key={i} className="hover:bg-transparent">
                      <TableCell colSpan={6}><Skeleton className="h-4 w-full" /></TableCell>
                    </TableRow>
                  ))
                : targets.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="font-medium text-ink">{t.name}</TableCell>
                      <TableCell><Badge variant="neutral">{t.provider}</Badge></TableCell>
                      <TableCell className="font-mono text-[0.8125rem]">{t.model}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {t.capabilities.map((c) => <Badge key={c} variant="neutral">{c}</Badge>)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={modelTargetTone[t.status]}>
                          {t.status === "healthy" ? "健康" : t.status === "degraded" ? "降级" : "不可达"}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-[0.8125rem]">
                        {t.circuitState === "closed" ? "关闭" : t.circuitState === "open" ? "熔断" : "半开"}
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <CredentialsCard />
    </div>
  );
}

function CredentialsCard() {
  const { data: credentials = [] } = useQuery(credentialsQueryOptions());

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>平台模型凭据</CardTitle>
        <p className="text-body-sm text-muted-foreground">密钥只展示绑定关系，不回显明文；凭据测试端点在 v1 未落地，暂不支持操作。</p>
      </CardHeader>
      <CardContent>
        <Table aria-label="平台模型凭据列表">
          <TableHeader>
            <TableRow>
              <TableHead>提供方</TableHead>
              <TableHead>绑定目标</TableHead>
              <TableHead>最近测试</TableHead>
              <TableHead>结果</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {credentials.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium text-ink">{c.providerName}</TableCell>
                <TableCell className="font-mono text-[0.8125rem]">{c.boundTargetId}</TableCell>
                <TableCell>{c.lastTestedAt ? formatDateTime(c.lastTestedAt) : "—"}</TableCell>
                <TableCell>
                  <Badge variant={c.lastTestResult === "ok" ? "success" : c.lastTestResult === "fail" ? "error" : "neutral"}>
                    {c.lastTestResult === "ok" ? "通过" : c.lastTestResult === "fail" ? "失败" : "未测试"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
