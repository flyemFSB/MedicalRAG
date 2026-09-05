"""MedicalRAG 领域核心边界：定义实体、值对象、状态机、策略、端口协议与确定性服务。

本包为纯领域层，不依赖任何外部框架与基础设施（无 FastAPI、SQLAlchemy、Redis、Qdrant、TaskIQ、LangGraph、Aegra），
遵循共享包边界规范。所有上层运行时（API、Agent、Worker）均统一依赖本包。
"""

__version__ = "0.1.0"
