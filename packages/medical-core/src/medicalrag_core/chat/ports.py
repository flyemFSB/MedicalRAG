"""聊天编排的适配器端口：精简显式的协议契约（spec 用户故事 36）。

端口仅声明编排所需的输入输出契约；具体实现（PostgreSQL / Redis / Qdrant / 外部模型提供商）
由 infra 基础设施包与应用组合根装配注入。医疗领域规则严格保留在领域层内，适配器无权决定编排流程。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ..evidence.evidence import Candidate
from ..intent.node import IntentNode
from ..intent.tree import ScoredIntent
from .model import (
    Analysis,
    ChatRequest,
    ChatResult,
    GenerationContext,
    IntentQuery,
    MemoryContext,
    Message,
)
from .run_state import ChatRunState


class ProviderUnavailableError(RuntimeError):
    """模型生成适配器整体不可用异常（经模型路由与故障转移后仍无法提供服务）。"""


class Memory(Protocol):
    """会话记忆端口：加载有界最近消息窗口（含摘要），按角色追加新消息并返回落库消息 ID。"""

    async def load(self, request: ChatRequest) -> MemoryContext: ...
    async def append(self, request: ChatRequest, message: Message) -> str | None: ...


class ConversationSummarizer(Protocol):
    """会话摘要端口（外部模型适配器）：将对话记录压缩为一段简短摘要文本。"""

    async def summarize(self, transcript: str) -> str: ...


class TermIntentResolver(Protocol):
    """查询词映射端口：将用户问题中命中的术语映射为强制纳入的意图候选（运营配置的确定性捷径）。"""

    async def resolve(self, question: str) -> tuple[ScoredIntent, ...]: ...


class IntentClassifier(Protocol):
    """意图分类器端口（外部模型适配器）：针对启用的叶子意图输出带分候选及短路响应文案。"""

    async def analyze(
        self,
        request: ChatRequest,
        leaves: tuple[IntentNode, ...],
        context: MemoryContext,
    ) -> Analysis: ...


class Retriever(Protocol):
    """混合检索适配器端口：根据解析出的意图查询（含槽位）并发检索并返回待融合候选。"""

    async def retrieve(
        self,
        request: ChatRequest,
        queries: tuple[IntentQuery, ...],
    ) -> tuple[Candidate, ...]: ...


class Generator(Protocol):
    """模型生成适配器端口：流式产出证据回答（Evidence Answer）；整体不可用时抛出 ProviderUnavailableError。"""

    def stream(self, context: GenerationContext) -> AsyncIterator[str]: ...


class RunRepository(Protocol):
    """业务 Run 记录持久化端口：负责创建 Run、记录状态迁移及落库最终结果。"""

    async def create_run(self, request: ChatRequest) -> str: ...
    async def record_state(self, run_id: str, state: ChatRunState) -> None: ...
    async def complete(self, run_id: str, result: ChatResult) -> None: ...
