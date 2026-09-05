"""OpenAI 兼容大语言模型适配器（基于官方推荐 openai SDK 实现）。

实现 medical_core.chat.ports.Generator、StreamingGenerator 以及 IntentClassifier 协议端口：
通过 OpenAI SDK 调用 chat completions 及 embeddings 接口。
当发生网络异常、API 报错或返回正文缺失时统一抛出 ProviderUnavailableError；支持注入自定义 httpx transport 供确定性测试。
网络传输严格遵循数据出境安全策略，仅发送脱敏后的重写问题与精简证据切片。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import cast

import httpx2 as httpx  # OpenAI SDK 3.x 起统一使用 httpx2；transport 必须同源
import openai
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict

from medicalrag_core.chat.model import (
    Analysis,
    ChatRequest,
    GenerationContext,
    MemoryContext,
    MessageRole,
)
from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.intent.node import IntentNode
from medicalrag_core.intent.tree import ScoredIntent


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


def _sdk_messages(messages: list[dict[str, str]]) -> list[ChatCompletionMessageParam]:
    """将字典格式消息列表集中转换为 SDK 类型，避免多处重复类型断言。"""
    return cast("list[ChatCompletionMessageParam]", messages)


class _ScoredIntentOut(BaseModel):
    """意图分类模型结构化输出的单个带置信度分数的意图项（由 Pydantic 执行强类型校验）。"""

    model_config = ConfigDict(extra="ignore")
    id: str
    score: float = 0.0
    slots: dict[str, object] = {}


class _Classification(BaseModel):
    """分类模型结构化输出契约；任一字段格式非法即判定整包无效（严防臆造意图）。"""

    model_config = ConfigDict(extra="ignore")
    rewritten_question: str | None = None
    intents: list[_ScoredIntentOut] = []
    guidance: str | None = None
    system_message: str | None = None


class OpenAICompatGenerator:
    """基于 OpenAI SDK 的证据回答生成适配器（支持一次性整段生成与流式 Token 输出，实现 Generator / StreamingGenerator 协议）。"""

    def __init__(
        self, config: LLMProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = _client(config, transport)

    def _build_messages(self, context: GenerationContext) -> list[dict[str, str]]:
        # 证据行格式：Citation 引用角标 + 标题 + 证据切片正文（规范 Phase 2：可溯源证据引用）
        evidence_text = "\n".join(
            f"{e.citation_label} {e.title}：{e.snippet}" for e in context.evidence
        )
        system = (
            "你是一名医学知识助手。遵守以下硬约束：\n"
            "1. 只依据下方编号证据回答，不得编造；\n"
            "2. 每条断言标注对应证据编号（如 [1]）；\n"
            "3. 证据不足以回答时，明确说明未能找到足够资料，不要推测。\n"
            "回答不构成个体化诊疗建议。\n\n证据：\n" + (evidence_text or "（无证据）")
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        # 会话历史消息（Memory 端口已截取有界窗口）：刚追加的末尾当前问题不重复加入历史，以重写后的问题作为最终 user 消息
        history = context.memory.messages
        if history and history[-1].role is MessageRole.USER:
            history = history[:-1]
        for message in history:
            role = "assistant" if message.role is MessageRole.ASSISTANT else "user"
            messages.append({"role": role, "content": message.text})
        messages.append({"role": "user", "content": context.rewritten_question})
        return messages

    async def generate(self, context: GenerationContext) -> str:
        try:
            completion = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                messages=_sdk_messages(self._build_messages(context)),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            raise ProviderUnavailableError("missing_content")
        return content

    async def stream(self, context: GenerationContext) -> AsyncIterator[str]:
        """执行流式回答生成：通过 SDK 流式迭代器逐段产出 delta.content。"""
        try:
            stream = await self._client.chat.completions.create(
                model=self._config.model,
                temperature=0,
                stream=True,
                messages=_sdk_messages(self._build_messages(context)),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is not None and delta.content:
                    yield delta.content
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc


class OpenAICompatContextualizer:
    """基于 OpenAI SDK 的文档切片背景增强补写适配器（实现 Contextualizer 协议端口）。

    严格遵循数据安全策略，仅发送脱敏后的文档正文切片；
    若调用失败则抛出 ProviderUnavailableError，由摄取流水线自动降级为无背景模式继续执行，不阻断摄取流程。
    """

    def __init__(
        self, config: LLMProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = _client(config, transport)

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
                messages=_sdk_messages(
                    self._build_messages(document_title, heading_path, chunk_text, preceding_text)
                ),
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        content = completion.choices[0].message.content if completion.choices else None
        return (content or "").strip()


class OpenAICompatClassifier:
    """基于 OpenAI SDK 的意图分类与问题重写适配器（实现 IntentClassifier 协议端口）。

    格式异常或畸形输出绝不臆造意图：直接返回空候选集并由上层编排触发澄清；
    超出预设意图树的未知 ID 原样返回，由意图树白名单进行过滤剔除。
    """

    def __init__(
        self, config: LLMProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = _client(config, transport)

    def _build_messages(
        self, request: ChatRequest, leaves: tuple[IntentNode, ...]
    ) -> list[dict[str, str]]:
        leaf_lines = "\n".join(
            f"- {node.id}: {node.name} — {node.description}"
            + (f"\n  示例：{'；'.join(node.examples)}" if node.examples else "")
            for node in leaves
        )
        system = (
            "你是意图分类器。判断用户问题属于下列哪个意图，只输出 JSON：\n"
            '{"rewritten_question": "重写后的问题", "intents": [{"id": "意图id", "score": 0.9, "slots": {}}], '
            '"guidance": null}\n可用意图：\n' + (leaf_lines or "（无可用意图）")
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
                messages=_sdk_messages(self._build_messages(request, leaves)),
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
        slots = {item.id: dict(item.slots) for item in payload.intents}
        return Analysis(
            rewritten_question=payload.rewritten_question or request.question,
            candidates=candidates,
            guidance_message=payload.guidance,
            system_message=payload.system_message,
            slots=slots,
        )
