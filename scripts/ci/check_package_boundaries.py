"""包边界合规检查（仅依赖标准库；违反架构边界退出码为 1）。

架构分层约束规则：
- medicalrag_core 严禁导入 medicalrag_infra 或任何 medicalrag_* 应用
- medicalrag_infra 严禁导入任何 medicalrag_* 应用
- 各应用之间（apps/*）严禁相互导入
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CORE = "medicalrag_core"
INFRA = "medicalrag_infra"
APPS = {
    "medicalrag_api": ROOT / "apps/api/src",
    "medicalrag_agent": ROOT / "apps/agent/src",
    "medicalrag_worker": ROOT / "apps/worker/src",
    "medicalrag_evaluation": ROOT / "apps/evaluation/src",
}

FORBIDDEN: dict[str, set[str]] = {
    CORE: {INFRA, *APPS},
    INFRA: set(APPS),
}
# apps 可依赖 packages；同级 apps 之间严禁相互导入。
for app in APPS:
    FORBIDDEN[app] = set(APPS) - {app}


def iter_py_files(base: Path):
    yield from base.rglob("*.py")


def package_of(path: Path) -> str | None:
    parts = path.parts
    if "medical-core" in parts:
        return CORE
    if "infra" in parts and "packages" in parts:
        return INFRA
    for name, src in APPS.items():
        if src in path.parents or path.parent == src:
            return name
    return None


def imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def main() -> int:
    search_roots = [
        ROOT / "packages/medical-core/src",
        ROOT / "packages/infra/src",
        *APPS.values(),
    ]
    violations: list[str] = []
    for base in search_roots:
        if not base.exists():
            continue
        for path in iter_py_files(base):
            pkg = package_of(path)
            if pkg is None:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(f"{path}: syntax error: {exc}")
                continue
            bad = imported_roots(tree) & FORBIDDEN[pkg]
            if bad:
                rel = path.relative_to(ROOT)
                violations.append(f"{pkg} {rel} imports forbidden: {sorted(bad)}")

    if violations:
        print("package boundary violations:")
        for line in violations:
            print(f"  - {line}")
        return 1
    print("package boundaries ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
