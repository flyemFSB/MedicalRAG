"""结构化日志检查（development-standards §3 红线；loguru）。"""

import pytest

from medicalrag_infra.logging import UnsafeLogField, _format, logger, safe_bind


def test_safe_fields_are_accepted():
    fields = safe_bind(request_id="r1", run_id="run-1", count=3)
    assert fields == {"request_id": "r1", "run_id": "run-1", "count": 3}


def test_forbidden_field_rejected():
    with pytest.raises(UnsafeLogField):
        safe_bind(request_id="r1", prompt="raw")


def test_unknown_field_rejected():
    with pytest.raises(UnsafeLogField):
        safe_bind(anything=1)


def test_logger_emits_safe_bound_fields_as_key_value():
    captured: list[str] = []
    logger.remove()
    logger.add(lambda s: captured.append(s), format=_format)
    logger.bind(**safe_bind(run_id="run-1", event_id="evt-1")).info("started")
    logger.remove()
    assert any("run_id=run-1" in s and "event_id=evt-1" in s for s in captured)
