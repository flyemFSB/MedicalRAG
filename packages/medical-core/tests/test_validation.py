"""索引校验检查（ADR 0013 发布门禁）。"""

from medicalrag_core.ingestion.validation import validate_index


def test_passes_when_all_checks_ok():
    result = validate_index(
        expected_chunks=3, indexed_chunks=3, checksum_ok=True, active_schema=True
    )
    assert result.passed
    assert result.reasons == ()


def test_fails_on_count_mismatch():
    result = validate_index(
        expected_chunks=3, indexed_chunks=2, checksum_ok=True, active_schema=True
    )
    assert not result.passed
    assert "Chunk 数量不一致" in result.reasons[0]


def test_fails_on_bad_checksum_or_schema():
    result = validate_index(
        expected_chunks=1, indexed_chunks=1, checksum_ok=False, active_schema=False
    )
    assert not result.passed
    assert len(result.reasons) == 2
