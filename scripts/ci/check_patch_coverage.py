"""变更行覆盖率门禁（ADR 0088）：你改的那几行必须被单元/契约层执行到。

为什么不是 `fail_under`：项目总量对「本次改动没被测」不敏感，且固定百分比会从地板退化成天花板
（`docs/research/quality-and-coverage-gates-best-practices.md` 第一节 6/7 条）。总量只守「不许回退」。

为什么需要本脚本而不是直接调 diff-cover：路径对不上时 diff-cover 会打印
「No lines with coverage information in this diff.」并以 **0** 退出——门禁静默失效，
和「本次只改了文档」无法区分。所以先做对齐校验：每条改动的 src 文件都必须出现在覆盖率报告里，
缺一条即失败（这条不变量一旦破坏，门禁就是假的）。

用法（CI 与本地同源）：
    uv run python scripts/ci/check_patch_coverage.py --base origin/main
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

from coverage import Coverage

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_PY_PATHSPEC = "*/src/*.py"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def changed_src_files(base: str) -> list[str]:
    """本次相对 base 改动/新增的 src 下的 Python 文件（删除的不算：报表里本就不该有）。"""
    result = _git("diff", "--diff-filter=d", "--name-only", f"{base}...HEAD", "--", SRC_PY_PATHSPEC)
    if result.returncode != 0:
        sys.exit(f"git diff 失败（base={base}）：{result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def configured_sources_doc() -> str:
    """错误信息里的配置文件位置（单一口径，避免两处各写一遍）。"""
    return "pyproject.toml 的 [tool.coverage.run] source"


def analysis_for_guard() -> Coverage:
    """门禁用的 coverage 分析器（只解析文件，不读数据）。"""
    return Coverage()


def measurable_files(paths: list[str]) -> list[str]:
    """剩下真正需要出现在覆盖率报告里的文件。

    用 coverage 自己的分析判定「有没有可测语句」，而不是自己数 AST 节点：
    只有模块 docstring 的 `__init__.py` 会被 coverage 判为空语句（不进报告），
    自己数节点会把它当有语句，守卫就会误拦这类改动。
    同时跳过工作区已删除的文件（本地比对历史提交时会遇到）。
    """
    analysis = analysis_for_guard()
    keep: list[str] = []
    for rel in paths:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            statements = analysis.analysis2(str(path))[1]
        except Exception:  # 解析不了就当需要覆盖，宁可报错也不要静默放过
            keep.append(rel)
            continue
        if statements:
            keep.append(rel)
    return keep


def report_index(report: pathlib.Path) -> dict[str, list[set[int]]]:
    """报告索引：`filename` → 各 class 的可执行行号集合。

    coverage.py 的 `filename` 相对各自的 source 根，所以不同根下同名文件（core 与 infra 都有
    `storage/`、`retrieval/`）会撞名。只看名字会把「缺失」误判成「已覆盖」，因此连行号集合一起比。
    """
    root = ET.parse(report).getroot()
    index: dict[str, list[set[int]]] = {}
    for package in root.iter("package"):
        for cls in package.findall("./classes/class"):
            filename = (cls.get("filename") or "").replace("\\", "/")
            lines = {int(ln.get("number") or 0) for ln in cls.iter("line")}
            index.setdefault(filename, []).append(lines)
    return index


def configured_sources() -> list[str]:
    """[tool.coverage.run] source 里配置的根（仓库相对路径）。

    必须看**配置**而不是报告的 `<sources>`：报告被 `--cov=<单个包>` 截窄正是要拦的漂移之一，
    拿报告自己的 source 当基准会把「没被度量」误降级成「不归我管」。
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return [
        str(entry).replace("\\", "/").strip("/")
        for entry in data["tool"]["coverage"]["run"]["source"]
    ]


def unreported_files(
    changed: list[str], report: pathlib.Path, analysis: Coverage
) -> tuple[list[str], list[str]]:
    """返回 (不在报告里的改动文件, 不在任何配置 source 下的改动文件)。"""
    index = report_index(report)
    sources = configured_sources()
    missing: list[str] = []
    outside: list[str] = []
    for rel in changed:
        root = next((src for src in sources if rel.startswith(src + "/")), None)
        if root is None:
            outside.append(rel)
            continue
        relative_name = rel[len(root) + 1 :]
        expected = set(analysis.analysis2(str(REPO_ROOT / rel))[1])
        candidates = index.get(relative_name, [])
        if not any(candidate == expected for candidate in candidates):
            missing.append(rel)
    return missing, outside


def main() -> int:
    parser = argparse.ArgumentParser(description="变更行覆盖率门禁")
    parser.add_argument("--base", required=True, help="比较基线（如 origin/main）")
    parser.add_argument("--report", default="coverage.xml", help="coverage.py XML 报告路径")
    parser.add_argument("--fail-under", type=float, default=80.0, help="变更行覆盖下限（百分比）")
    args = parser.parse_args()

    report = pathlib.Path(args.report)
    if not report.is_absolute():
        report = REPO_ROOT / report
    if not report.exists():
        return _fail(f"找不到覆盖率报告 {report}；CI 里应先跑 pytest --cov-report=xml")

    if _git("rev-parse", "--verify", "--quiet", args.base).returncode != 0:
        return _fail(f"基线 {args.base} 在本地不存在（浅克隆？需要 fetch-depth: 0）")

    changed = measurable_files(changed_src_files(args.base))
    if not changed:
        print(f"本次未改动可测的 {SRC_PY_PATHSPEC} 文件，变更行门禁跳过（无对象可判）。")
        return 0

    missing, outside = unreported_files(changed, report, analysis_for_guard())
    if outside:
        print(
            "::warning::以下改动文件不在 pyproject.toml 的 [tool.coverage.run] source 内，覆盖率未被度量：",
            file=sys.stderr,
        )
        for path in outside:
            print(f"  - {path}", file=sys.stderr)
    if missing:
        print("::error::以下改动文件不在覆盖率报告里，变更行门禁无法判定：", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        print(
            "报告缺失即门禁失效（diff-cover 会以 0 退出）。检查 pyproject.toml 的 "
            "[tool.coverage.run] source 与 relative_files。",
            file=sys.stderr,
        )
        return 1

    diff_cover = shutil.which("diff-cover")
    if diff_cover is None:
        return _fail("找不到 diff-cover（应在 dev dependency group 中）")

    print(f"变更行门禁：{len(changed)} 个 src 文件改动，下限 {args.fail_under:g}%\n")
    result = subprocess.run(
        [
            diff_cover,
            str(report),
            f"--compare-branch={args.base}",
            f"--fail-under={args.fail_under:g}",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode


def _fail(message: str) -> int:
    print(f"::error::{message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
