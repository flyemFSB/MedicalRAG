# ADR 0080: 生产化加固基线（CI 门禁、类型检查、可观测、供应链与运行时安全）

日期：2026-08-24
状态：已接受

## 背景

架构评审（2026-08-24）结论：领域分层与 ADR 纪律达标，但工程闭环缺失——文档声称的
三级测试门禁无机器强制（无 CI）、Python 无类型检查、指标为进程内 JSON 无法抓取、
日志缺 request_id 关联、镜像 root 单阶段运行且迁移随启动并发执行、中间件端口对外暴露、
Langfuse 带弱默认密钥、xlsx 依赖携带已知 CVE 且 npm 源停更、outbox 无毒消息处理、
worker 配置绕过 fail-fast 校验。另发现两处被类型检查暴露的真实运行时 bug
（qdrant `set_payload` 参数名错误、`broker.kick` 参数形状错误）。

## 决策

1. **CI 强制门禁**（`.github/workflows/ci.yml`）：提交级 = ruff format/check +
   pyright(basic) + pytest(覆盖率 ≥80%，基线 82%)；PR 级 = OpenAPI 契约导出与
   contract-check + turbo lint/typecheck/test:unit/build + gitleaks/pip-audit/
   pnpm audit + 四镜像构建。集成/E2E/eval-answer 属合并级，本地或发布流水线执行。
2. **Python 类型检查**：pyright basic 起步（根 `[tool.pyright]`），逐步收紧；
   env 注入型 Settings 的 `reportCallIssue` 允许定点 ignore。
3. **读路径零写**：Workspace 创建与 operator 升级只在 register/login 认证事件上
   （`ensure_workspace`）；`current_user` 变纯读。cookie 命名单一出口
   `settings.session_cookie_name`，消除 deps→api.auth 私有符号反向依赖。
4. **登录防爆破**：按来源 IP 固定窗口限流（`auth_rate_limit` 默认 10/min）。
5. **可观测落地**：ASGI `request_id` 中间件（接受上游 X-Request-ID，绑定 loguru
   contextvars 并回写响应头）；`/metrics` 输出 Prometheus 文本格式
   （counter/gauge/summary quantiles），`/api/metrics` JSON 仅作人工排查面。
6. **流式 payload 单一出口**：领域事件自带 `sse_name`/`to_payload`
   （Evidence/SafetyAssessment/Analysis 同样），SSE 端点与 agent graph 共用，
   新增字段不漏消费方。
7. **Worker 加固**：TaskIQ 组合根改 pydantic-settings（启动即校验）；outbox 增加
   `attempts` 列 + `record_failure`，relay 单条失败计数不阻塞批次，超过
   `outbox_max_attempts`（默认 5）由 claim 过滤跳过（毒消息保持未处理可见）。
8. **部署拓扑**：迁移独立一次性 Job（api depends_on 完成），镜像多阶段 + 非 root
   （uid 10001）+ 预建对象存储卷；中间件端口仅绑 127.0.0.1；服务加资源上限；
   api 与 worker 共享 objects 卷同路径；Langfuse 密钥无默认值（空值即拒绝启动，
   fail-open 语义不变，ADR 0059/0076）。
9. **集成测试层**：compose `test` profile 提供 PG/Redis/Qdrant（宿主端口错开、
   tmpfs）；pytest `integration` 标记 + `MEDICALRAG_TEST_DATABASE_URL` 未配置即跳过。
10. **前端质量层**：web 补 vitest（test:unit 进 turbo 门禁）与 Playwright 冒烟
    （认证流/健康面，针对 compose 全栈）；移除 npm 源 `xlsx`（0.18.5 已知 CVE 且
    上游停更于 npm），XLSX 内嵌预览降级为不支持（ADR 0068 范围修订记录于此）。
11. **流程配套**：pre-commit（ruff 双钩子+基础卫生）、Renovate（含锁文件维护）、
    CODEOWNERS、SECURITY.md、威胁模型（docs/security-threat-model.md）。

## 后果

- 文档门禁全部机器化；两处潜伏运行时 bug 在引入类型检查当天即被捕获修复，
  证明该门禁成本合理。
- xlsx 预览能力降级；如需恢复，须引入官方 CDN 源或维护分叉并重过供应链审计。
- pyright basic 是起点而非终点；strict 化按包渐进（core 先行）。
- 迁移 Job 使 `docker compose up` 多一个前置容器；K8s 化时对应 initContainer/Job。

## 参考

- docs/research/devops-quality-security-and-observability.md
- docs/security-threat-model.md
- ADR 0013/0049/0053/0059/0061/0063/0071/0072/0073/0075/0076
