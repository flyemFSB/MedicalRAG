"""生产入口契约检查：aegra.json 按字符串路径装配图与认证。

`apps/agent/aegra.json` 用 `"./src/medicalrag_agent/entry.py:graph"` / `:auth` 装载生产图，
Python 侧没有任何 import 引用它们——所以「改名、搬文件、改属性名」既不会被静态检查发现，
也不会被其它测试发现，只会在部署时炸。本测试是那道闸，同时把入口模块拉进覆盖率口径。
"""

import importlib
import json
import pathlib

from langgraph_sdk import Auth

_AGENT_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CONFIG = json.loads((_AGENT_ROOT / "aegra.json").read_text(encoding="utf-8"))


def _resolve(spec: str) -> object:
    """把 aegra.json 的 "./src/x/y.py:attr" 解析为真实对象（不依赖 aegra 内部机制）。"""
    path, _, attribute = spec.rpartition(":")
    module_path = (_AGENT_ROOT / path).resolve().relative_to(_AGENT_ROOT / "src").with_suffix("")
    module = importlib.import_module(".".join(module_path.parts))
    return getattr(module, attribute)


def test_declared_graph_entry_point_resolves_to_callable():
    """graphs.agent 指到的对象必须存在且可调用（Aegra 以工厂方式构造图）。"""
    assert callable(_resolve(_CONFIG["graphs"]["agent"]))


def test_declared_auth_entry_point_is_an_auth_instance():
    """Aegra 只接受 langgraph_sdk.Auth 实例；指向函数或其它类型会在启动时失败。"""
    assert isinstance(_resolve(_CONFIG["auth"]["path"]), Auth)
