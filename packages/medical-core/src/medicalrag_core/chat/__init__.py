"""聊天领域：Run 状态机契约与确定性编排核心（spec「The seam」）。

apps/agent 中的 LangGraph 流水线是执行者；本包提供状态机、值对象、端口与
ChatPipeline 编排核心。每个终止态都会持久化用户消息、助手结果/错误事件与
业务 Run 完成记录。
"""
