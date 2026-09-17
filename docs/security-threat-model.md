# 威胁模型（v1 基线，ADR 0080 记录）

范围：同源 Web 工作台（Nginx + Vite SPA）、FastAPI 组合根、Aegra agent、TaskIQ worker、
PG/Redis/Qdrant 中间件。**v1 不含可识别患者数据（ADR 0008）**；本模型随成员模型与
患者数据引入必须重评。

## 信任边界

```
浏览器 ──HTTPS──▶ Nginx(8080) ──▶ FastAPI(api:8000) / Aegra(agent:2026)
                                        │
                    TaskIQ(worker) ◀── Redis 队列 / PG outbox
                                        │
                          外部 LLM/嵌入/Reranker/MinerU Provider
```

中间件不对外暴露端口（compose 仅绑 127.0.0.1）；应用容器非 root 运行。

## 主要威胁与缓解

| # | 威胁 | 缓解 | 残余风险 |
| --- | --- | --- | --- |
| T1 | 会话窃取/固定 | HttpOnly+Secure+SameSite=Strict cookie；登录/注册轮换令牌；服务端会话可吊销 | 无 HSTS 终结在反代层，部署时需配 TLS |
| T2 | 凭据填充/爆破 | 登录按来源 IP 固定窗口限流（`auth_rate_limit`） | 分布式爆破需后续 WAF/验证码 |
| T3 | 越权访问运营面 | `require_operator` 依赖 + OPERATOR_EMAILS 白名单；读路径零写（ADR 0080） | 邮箱名单即权限边界，需流程保护 |
| T4 | 提示注入外泄系统约束 | 受控有界流水线（非开环 ReAct）；生成证据有界（ADR 0040） | 对抗性文档内容进入证据的间接注入，靠安全评估层兜底 |
| T5 | 医疗危害输出 | PROHIBITED 检索前短路（ADR 0043）；固定免责声明（ADR 0042）；空证据拒绝生成 | 专家审核不可自动化（spec 红线） |
| T6 | 日志泄露敏感内容 | `SAFE_FIELDS` 白名单在输出汇聚点 `_format` 强制过滤（绕过绑定层也拦得住） | 自定义字段新增时需评审 SAFE_FIELDS |
| T7 | 密钥入库 | gitleaks CI 扫描；`.env` 入 .gitignore；无默认弱密钥（Langfuse 空值即拒绝启动） | 开发机泄露不在扫描范围 |
| T8 | 供应链投毒 | 镜像钉 tag；Renovate 升级评审；pip-audit/pnpm audit 门禁 | 未做镜像 digest 钉版（升级时补） |
| T9 | 毒消息阻塞摄取管道 | outbox attempts 计数 + 上限跳过（ADR 0080） | 死信仍需操作员手工处理 |
| T10 | 拒绝服务（认证后） | 每用户聊天限流；provider 失败降级为 FALLBACK | 未做全局并发上限 |

## 不在 v1 范围

- 多租户隔离审计、字段级加密、恶意软件扫描（ADR 0029）、WAF/DDoS 防护。
