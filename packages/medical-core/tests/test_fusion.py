"""证据融合检查（ADR 0039）。"""

from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.fusion import fuse
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy


def _candidate(**overrides) -> Candidate:
    defaults = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "source_id": "src-1",
        "title": "t",
        "snippet": "s",
        "intent": "disease",
        "channel": "dense",
        "score": 0.5,
    }
    defaults.update(overrides)
    return Candidate(**defaults)


def test_empty_input():
    assert fuse([], RetrievalPolicy(version=1, context_cap=10)) == ()


def test_ineligible_candidates_are_dropped():
    result = fuse(
        [_candidate(chunk_id="a", is_eligible=False)],
        RetrievalPolicy(version=1, context_cap=10),
    )
    assert result == ()


def test_dedup_merges_provenance_and_keeps_highest_score():
    result = fuse(
        [
            _candidate(chunk_id="c1", channel="dense", score=0.4),
            _candidate(chunk_id="c1", channel="sparse", score=0.9, intent="drug"),
        ],
        RetrievalPolicy(version=3, context_cap=10),
    )
    assert len(result) == 1
    evidence = result[0]
    assert evidence.chunk_id == "c1"
    assert evidence.channel_provenance == frozenset({"dense", "sparse"})
    assert evidence.intent_provenance == frozenset({"disease", "drug"})
    assert evidence.raw_score == 0.9
    assert evidence.score == 0.9
    assert evidence.policy_version == 3


def test_reranker_score_takes_precedence_for_ordering():
    candidates = [
        _candidate(chunk_id="raw-hi", score=0.9),
        _candidate(chunk_id="reranked", score=0.1, reranker_score=0.95),
    ]
    result = fuse(candidates, RetrievalPolicy(version=1, context_cap=10))
    assert result[0].chunk_id == "reranked"
    assert result[1].chunk_id == "raw-hi"
    assert result[0].raw_score == 0.1
    assert result[0].score == 0.95


def test_intent_priority_breaks_ties():
    candidates = [
        _candidate(chunk_id="a", intent="disease", score=0.5),
        _candidate(chunk_id="b", intent="drug", score=0.5),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, intent_priority={"drug": 3, "disease": 1})
    result = fuse(candidates, policy)
    assert result[0].chunk_id == "b"


def test_channel_quota_is_enforced():
    candidates = [
        _candidate(chunk_id="d1", channel="dense", score=0.9),
        _candidate(chunk_id="d2", channel="dense", score=0.8),
        _candidate(chunk_id="s1", channel="sparse", score=0.7),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, channel_quotas={"dense": 1})
    result = fuse(candidates, policy)
    assert [e.chunk_id for e in result] == ["d1", "s1"]


def test_intent_quota_is_enforced():
    candidates = [
        _candidate(chunk_id="i1", intent="disease", score=0.9),
        _candidate(chunk_id="i2", intent="disease", score=0.8),
        _candidate(chunk_id="j1", intent="drug", score=0.7),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, intent_quota=1)
    result = fuse(candidates, policy)
    assert [e.chunk_id for e in result] == ["i1", "j1"]


def test_context_cap_limits_and_labels_are_sequential():
    candidates = [_candidate(chunk_id=f"c{i}", score=(10 - i) / 10) for i in range(5)]
    result = fuse(candidates, RetrievalPolicy(version=1, context_cap=3))
    assert [e.chunk_id for e in result] == ["c0", "c1", "c2"]
    assert [e.citation_label for e in result] == ["[1]", "[2]", "[3]"]
