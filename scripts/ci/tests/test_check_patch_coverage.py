"""变更行门禁判定逻辑的回归测试。

为什么需要：``scripts/ci/check_patch_coverage.py`` 的唯一职责是「改动没被测就红」，
而它自己失守时的表现是**静默放行**（diff-cover 在路径对不上时以 0 退出）。
因此这里给它一个最小可证伪面：对齐守卫的判定函数。

只测纯判定（不跑 git、不跑 diff-cover 子进程）：那两段是现场输入，
由 CI 里的真实 diff 与真实报告覆盖；这里钉的是「报告与改动对不上时必须判 missing」。
"""

import importlib.util
import pathlib

_GATE_PATH = pathlib.Path(__file__).resolve().parents[1] / "check_patch_coverage.py"
_spec = importlib.util.spec_from_file_location("check_patch_coverage", _GATE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

# 取自仓库真实受度量文件（语句集合运行时计算，文件内容变更不会让测试失真）
_REL = "packages/medical-core/src/medicalrag_core/ids.py"
_REPORT_NAME = "ids.py"  # 报告里的 filename 相对各自的 source 根


def _statements(rel: str) -> list[int]:
    return sorted(gate.analysis_for_guard().analysis2(str(gate.REPO_ROOT / rel))[1])


def _report(tmp_path: pathlib.Path, filename: str, lines: list[int]) -> pathlib.Path:
    entries = "".join(f'<line number="{n}" hits="1"/>' for n in lines)
    xml = (
        '<?xml version="1.0" ?><coverage><sources><source>.</source></sources>'
        f'<packages><package name="."><classes><class filename="{filename}" name="{filename}">'
        f"<lines>{entries}</lines></class></classes></package></packages></coverage>"
    )
    path = tmp_path / "coverage.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_changed_file_with_matching_statements_is_accepted(tmp_path):
    report = _report(tmp_path, _REPORT_NAME, _statements(_REL))

    missing, outside = gate.unreported_files([_REL], report, gate.analysis_for_guard())

    assert (missing, outside) == ([], [])


def test_changed_file_missing_from_report_is_reported(tmp_path):
    """报告被 --cov=<单包> 截窄或过期时：必须判 missing（否则门禁静默永不触发）。"""
    statements = _statements(_REL)
    assert len(statements) > 1, "样本文件语句太少，无法构造「少一行」的场景"
    report = _report(tmp_path, _REPORT_NAME, statements[:-1])

    missing, _ = gate.unreported_files([_REL], report, gate.analysis_for_guard())

    assert missing == [_REL]


def test_changed_file_outside_configured_sources_is_classified(tmp_path):
    """不在 [tool.coverage.run] source 内的改动只能告警，不能算已度量。"""
    report = _report(tmp_path, _REPORT_NAME, _statements(_REL))
    outside_rel = "scripts/ci/check_patch_coverage.py"

    missing, outside = gate.unreported_files([outside_rel], report, gate.analysis_for_guard())

    assert (missing, outside) == ([], [outside_rel])


def test_report_index_keeps_statement_sets_per_duplicate_filename(tmp_path):
    """同名文件（core/infra 都有 storage/、retrieval/）靠行号集合区分，不能只看文件名。"""
    entries = "".join(f'<line number="{n}" hits="1"/>' for n in (1, 2))
    xml = (
        '<?xml version="1.0" ?><coverage><sources><source>.</source></sources><packages>'
        '<package name="a"><classes><class filename="dup.py" name="dup.py">'
        f"<lines>{entries}</lines></class></classes></package>"
        '<package name="b"><classes><class filename="dup.py" name="dup.py">'
        '<lines><line number="7" hits="1"/></lines></class></classes></package>'
        "</packages></coverage>"
    )
    report = tmp_path / "dup.xml"
    report.write_text(xml, encoding="utf-8")

    index = gate.report_index(report)

    assert index["dup.py"] == [{1, 2}, {7}]
