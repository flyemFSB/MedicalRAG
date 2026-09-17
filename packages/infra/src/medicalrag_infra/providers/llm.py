"""OpenAI 兼容大语言模型适配器（基于官方推荐 openai SDK 实现）。

实现 medical_core.chat.ports.Generator、StreamingGenerator 以及 IntentClassifier 协议端口：
通过 OpenAI SDK 调用 chat completions 及 embeddings 接口。
当发生网络异常、API 报错或返回正文缺失时统一抛出 ProviderUnavailableError；支持注入自定义 httpx transport 供确定性测试。
网络传输严格遵循数据出境安全策略，仅发送脱敏后的重写问题与精炼证据分块。
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import cast

import httpx2 as httpx  # OpenAI SDK 3.x 起统一使用 httpx2；transport 必须同源
import openai
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from medicalrag_core.chat.model import (
    Analysis,
    ChatRequest,
    GenerationContext,
    MemoryContext,
    MessageRole,
)
from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.evidence.evidence import Evidence
from medicalrag_core.intent.node import IntentNode
from medicalrag_core.intent.tree import ScoredIntent

# 引用角标（如 [1]）在进入历史前剥离：角标只服务单轮 UI 溯源，
# 留在记忆里会成为下一轮改写与生成的上下文噪声（对齐参考实现 CitationMarkup.strip 语义）
_CITATION_MARK_RE = re.compile(r"\s*\[\d+\]")


def _strip_citations(text: str) -> str:
    return _CITATION_MARK_RE.sub("", text)


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    """外部大语言模型提供商配置；api_key 仅通过环境变量或安全密钥管理器注入，严禁硬编码在代码库中。"""

    base_url: str
    api_key: str | None = None
    model: str = "gpt-4o-mini"
    timeout_s: float = 30.0


def _client(
    config: LLMProviderConfig, transport: httpx.AsyncBaseTransport | None
) -> openai.AsyncOpenAI:
    """构造 SDK 异步客户端（base_url 自动补齐 /v1 前缀；无密钥时填充占位以支持确定性测试）。"""
    return openai.AsyncOpenAI(
        api_key=config.api_key or "unset",
        base_url=f"{config.base_url.rstrip('/')}/v1",
        timeout=config.timeout_s,
        http_client=httpx.AsyncClient(transport=transport) if transport is not None else None,
    )


class _OpenAICompatClient:
    """OpenAI SDK 适配器公共基类：持有 SDK 客户端并在停机时释放连接池。"""

    def __init__(
        self, config: LLMProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = _client(config, transport)

    async def aclose(self) -> None:
        """释放底层 SDK 客户端持有的 HTTP 连接池（组合根停机时调用）。"""
        await self._client.close()


class _ScoredIntentOut(BaseModel):
    """意图分类模型结构化输出的单个带置信度分数的意图项（由 Pydantic 执行强类型校验）。"""

    id: str
    score: float = 0.0


class _Classification(BaseModel):
    """分类模型结构化输出契约；任一字段格式非法即判定整包无效（严防臆造意图）。"""

    rewritten_question: str | None = None
    sub_questions: list[str] = []
    intents: list[_ScoredIntentOut] = []
    guidance: str | None = None
    system_message: str | None = None


class OpenAICompatGenerator(_OpenAICompatClient):
    """基于 OpenAI SDK 的证据回答生成适配器（支持一次性整段生成与流式 Token 输出，实现 Generator / StreamingGenerator 协议）。"""

    def _build_messages(self, context: GenerationContext) -> list[dict[str, str]]:
        # 证据按文档分组渲染（组间保持相关性序、组内按引用编号序），prompt 刻意不含文档标题：
        # 标题会诱发「出自《XX》」式归因幻觉（对齐参考实现 DefaultContextFormatter 的设计）；
        # 标题仅随 Evidence 事件供前端证据面板展示。
        by_document: dict[str, list[Evidence]] = {}
        for item in context.evidence:
            by_document.setdefault(item.document_id, []).append(item)
        evidence_lines: list[str] = []
        for document_id, items in by_document.items():
            evidence_lines.append(f"文档 {document_id}：")
            evidence_lines.extend(f"{e.citation_label} {e.snippet}" for e in items)
        evidence_text = "\n".join(evidence_lines)
        system = (
            "你是一名医学知识助手。遵守以下硬约束：\n"
            "1. 只依据下方编号证据回答，不得编造；\n"
            "2. 每条断言标注对应证据编号（如 [1]）；\n"
            "3. 证据不足以回答时，明确说明未能找到足够资料，不要推测。\n"
            "回答不构成个体化诊疗建议。\n\n证据：\n" + (evidence_text or "（无证据）")
        )
        if context.analysis:
            # Analysis Depth（ADR 0069）：深度综合模式——生成器此前忽略该标志，现按契约生效
            system += (
                "\n当前为深度分析模式：请综合全部证据给出更完整、结构化的解答，"
                "并指明证据之间的分歧或局限。"
            )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        # 会话历史消息（Memory 端口已截取有界窗口）：刚追加的末尾当前问题不重复加入历史，以重写后的问题作为最终 user 消息
        history = context.memory.messages
        if history and history[-1].role is MessageRole.USER:
            history = history[:-1]
        for message in history:
            if message.role is MessageRole.SYSTEM:
                # 会话摘要等系统级上下文以 system 角色注入（不冒充用户发言）
                messages.append({"role": "system", "content": message.text})
            else:
                role = "assistant" if message.role is MessageRole.ASSISTANT else "user"
                content = (
                    _strip_citations(message.text)
                    if message.role is MessageRole.ASSISTANT
                    else message.text
                )
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": context.rewritten_question})
        return messages

    async def generate(self, context: GenerationContext) -> str:
        try:
            completion = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                messages=cast("list[ChatCompletionMessageParam]", self._build_messages(context)),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            raise ProviderUnavailableError("missing_content")
        return content

    async def stream(self, context: GenerationContext) -> AsyncIterator[str]:
        """执行流式回答生成：优先用官方 `.stream()` 上下文管理器（客户端取消/提前退出时可靠关闭响应）。

        `create(stream=True)` + 手工迭代在取消/异常路径上不会关闭底层 HTTP 响应，
        连接无法归还连接池（官方 helpers 文档明确要求 `.stream()` 必须配上下文管理器）。
        """
        try:
            async with self._client.chat.completions.stream(
                model=self._config.model,
                temperature=0,
                messages=cast("list[ChatCompletionMessageParam]", self._build_messages(context)),
            ) as stream:
                async for event in stream:
                    if event.type == "content.delta" and event.delta:
                        yield event.delta
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc


class OpenAICompatContextualizer(_OpenAICompatClient):
    """基于 OpenAI SDK 的文档分块上下文背景补写适配器（实现 Contextualizer 协议端口）。

    严格遵循数据安全策略，仅发送脱敏后的文档正文分块；
    若调用失败则抛出 ProviderUnavailableError，由摄取流水线自动降级为无背景模式继续执行，不阻断摄取流程。
    """

    def _build_messages(
        self,
        document_title: str,
        heading_path: Sequence[str],
        chunk_text: str,
        preceding_text: str,
    ) -> list[dict[str, str]]:
        system = (
            "你是医学文档索引助手。给定文档标题、章节路径、前文摘录和当前片段，"
            "用 50-100 字写一段背景说明：这个片段讨论什么、位于文档的什么位置。"
            "只输出说明文字本身。"
        )
        user = (
            f"文档标题：{document_title}\n"
            f"章节路径：{' > '.join(heading_path) if heading_path else '（无）'}\n"
            f"前文摘录：{preceding_text[:500] or '（无）'}\n"
            f"当前片段：\n{chunk_text}"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def situate(
        self,
        *,
        document_title: str,
        heading_path: Sequence[str],
        chunk_text: str,
        preceding_text: str,
    ) -> str:
        try:
            completion = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                messages=cast(
                    "list[ChatCompletionMessageParam]",
                    self._build_messages(document_title, heading_path, chunk_text, preceding_text),
                ),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        content = completion.choices[0].message.content if completion.choices else None
        return (content or "").strip()


class OpenAICompatClassifier(_OpenAICompatClient):
    """基于 OpenAI SDK 的意图分类与问题重写适配器（实现 IntentClassifier 协议端口）。

    格式异常或畸形输出绝不臆造意图：直接返回空候选集并由上层编排触发澄清；
    超出预设意图树的未知 ID 原样返回，由意图树白名单进行过滤剔除。
    """

    def _build_messages(
        self, request: ChatRequest, leaves: tuple[IntentNode, ...]
    ) -> list[dict[str, str]]:
        leaf_lines = "\n".join(
            f"- {node.id}: {node.name} — {node.description}"
            + (f"\n  示例：{'；'.join(node.examples)}" if node.examples else "")
            for node in leaves
        )
        system = (
            "你是意图分类器。判断用户问题属于下列哪个意图；如属多轮对话或指代不明，"
            "请结合上下文重写问题，并可将其拆分为最多 3 个更具体的子问题。只输出 JSON：\n"
            '{"rewritten_question": "重写后的问题", "sub_questions": ["子问题1", "子问题2"], '
            '"intents": [{"id": "意图id", "score": 0.9}], "guidance": null}\n可用意图：\n'
            + (leaf_lines or "（无可用意图）")
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": request.question},
        ]

    async def analyze(
        self,
        request: ChatRequest,
        leaves: tuple[IntentNode, ...],
        context: MemoryContext,
    ) -> Analysis:
        try:
            completion = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                messages=cast(
                    "list[ChatCompletionMessageParam]", self._build_messages(request, leaves)
                ),
            )
        except openai.APIError:
            # 分类器不可用时返回空候选集，绝不臆造意图，由上层流水线进入兜底澄清分支
            return Analysis(rewritten_question=request.question, candidates=())
        content = completion.choices[0].message.content if completion.choices else None
        if content is None:
            return Analysis(rewritten_question=request.question, candidates=())
        return self._parse(request, content)

    def _parse(self, request: ChatRequest, content: str) -> Analysis:
        # Pydantic 结构化校验：任何字段畸形均视为整包无效，坚决避免臆造错误意图
        try:
            payload = _Classification.model_validate_json(content)
        except ValueError:
            return Analysis(rewritten_question=request.question, candidates=())
        candidates = tuple(
            ScoredIntent(node_id=item.id, score=item.score) for item in payload.intents
        )
        sub_questions = tuple(s.strip() for s in payload.sub_questions if s and s.strip())
        return Analysis(
            rewritten_question=payload.rewritten_question or request.question,
            candidates=candidates,
            guidance_message=payload.guidance,
            system_message=payload.system_message,
            sub_questions=sub_questions,
        )


class OpenAICompatSummarizer(_OpenAICompatClient):
    """基于 OpenAI SDK 的会话摘要适配器（实现 ConversationSummarizer 协议端口）。

    将溢出记忆窗口的早期对话压缩为一段简短摘要；失败时抛出 ProviderUnavailableError，
    由记忆仓储降级为本次不做压缩（不阻断聊天主流程）。
    """

    async def summarize(self, transcript: str) -> str:
        system = (
            "你是会话摘要助手。把对话记录压缩为一段不超过 300 字的摘要，"
            "保留关键医学事实、用户关注点与已给出的结论；只输出摘要本身。"
        )
        try:
            completion = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                messages=cast(
                    "list[ChatCompletionMessageParam]",
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": transcript[:6000]},
                    ],
                ),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        content = completion.choices[0].message.content if completion.choices else None
        return (content or "").strip()
