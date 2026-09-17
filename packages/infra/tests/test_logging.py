"""结构化日志检查（development-standards §3 红线；loguru）。"""

from medicalrag_infra.logging import _format, configure, logger


def _capture(emit) -> list[str]:
    """把 logger 输出重定向到内存列表，返回捕获到的日志行。"""
    captured: list[str] = []
    logger.remove()
    logger.add(lambda s: captured.append(s), format=_format)
    try:
        emit()
    finally:
        logger.remove()
    return captured


def test_whitelisted_field_is_emitted_as_key_value():
    captured = _capture(lambda: logger.bind(run_id="run-1", event_id="evt-1").info("started"))
    assert any("run_id=run-1" in s and "event_id=evt-1" in s for s in captured)


def test_unknown_field_never_reaches_output():
    """白名单外的字段（如原始 prompt）不得落盘：校验在输出汇聚点，绕过 logger.bind 也拦得住。"""
    captured = _capture(lambda: logger.bind(run_id="run-1", prompt="原始病历正文").info("x"))
    assert any("run_id=run-1" in s for s in captured)
    assert all("原始病历正文" not in s and "prompt=" not in s for s in captured)


def test_exception_traceback_is_rendered():
    """函数式 format 必须自行渲染异常，否则 logger.exception() 的堆栈会消失。"""

    def boom() -> None:
        try:
            raise RuntimeError("探测失败")
        except RuntimeError:
            logger.exception("节点异常")

    captured = _capture(boom)
    assert any("RuntimeError: 探测失败" in s for s in captured)


def test_configure_never_dumps_exception_locals(capsys):
    """生产 sink（diagnose=False）不得把异常帧里的局部变量（含凭据）写进日志。"""
    secret = "LEAK_ME_API_TOKEN"
    configure(level="INFO")
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("节点异常")
    finally:
        logger.remove()
    out = capsys.readouterr().err
    assert "RuntimeError: boom" in out
    assert secret not in out
