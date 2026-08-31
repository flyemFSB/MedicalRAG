"""证据融合检查（ADR 0039）。"""

from medicalrag_core.evidence.evidence import Candidate, DroppedCandidate
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
    result = fuse([], RetrievalPolicy(version=1, context_cap=10))
    assert result.evidence == ()
    assert result.dropped == ()


def test_ineligible_candidates_are_dropped():
    result = fuse(
        [_candidate(chunk_id="a", is_eligible=False)],
        RetrievalPolicy(version=1, context_cap=10),
    )
    assert result.evidence == ()
    assert result.dropped[0].reason == "publication_not_eligible"


def test_dedup_merges_provenance_and_keeps_highest_score():
    result = fuse(
        [
            _candidate(chunk_id="c1", channel="dense", score=0.4),
            _candidate(chunk_id="c1", channel="sparse", score=0.9, intent="drug"),
        ],
        RetrievalPolicy(version=3, context_cap=10),
    )
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.chunk_id == "c1"
    assert evidence.channel_provenance == frozenset({"dense", "sparse"})
    assert evidence.intent_provenance == frozenset({"disease", "drug"})
    assert evidence.raw_score == 0.9
    assert evidence.score == 0.9
    assert evidence.policy_version == 3


def test_reranker_score_takes_precedence_for_ordering():
    # 通道分数更低、但归一化 Reranker 分数更高的候选，必须排在无 Reranker 分数的候选之前。
    candidates = [
        _candidate(chunk_id="raw-hi", score=0.9),
        _candidate(chunk_id="reranked", score=0.1, reranker_score=0.95),
    ]
    result = fuse(candidates, RetrievalPolicy(version=1, context_cap=10))
    assert result.evidence[0].chunk_id == "reranked"
    assert result.evidence[1].chunk_id == "raw-hi"
    assert result.evidence[0].raw_score == 0.1
    assert result.evidence[0].score == 0.95


def test_source_quality_breaks_ties():
    candidates = [
        _candidate(chunk_id="low", score=0.5, source_quality=1),
        _candidate(chunk_id="high", score=0.5, source_quality=5),
    ]
    result = fuse(candidates, RetrievalPolicy(version=1, context_cap=10))
    assert result.evidence[0].chunk_id == "high"


def test_intent_priority_breaks_ties():
    candidates = [
        _candidate(chunk_id="a", intent="disease", score=0.5),
        _candidate(chunk_id="b", intent="drug", score=0.5),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, intent_priority={"drug": 3, "disease": 1})
    result = fuse(candidates, policy)
    assert result.evidence[0].chunk_id == "b"


def test_channel_quota_is_enforced():
    candidates = [
        _candidate(chunk_id="d1", channel="dense", score=0.9),
        _candidate(chunk_id="d2", channel="dense", score=0.8),
        _candidate(chunk_id="s1", channel="sparse", score=0.7),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, channel_quotas={"dense": 1})
    result = fuse(candidates, policy)
    assert [e.chunk_id for e in result.evidence] == ["d1", "s1"]
    assert result.dropped[0].reason == "channel_quota"


def test_intent_quota_is_enforced():
    candidates = [
        _candidate(chunk_id="i1", intent="disease", score=0.9),
        _candidate(chunk_id="i2", intent="disease", score=0.8),
        _candidate(chunk_id="j1", intent="drug", score=0.7),
    ]
    policy = RetrievalPolicy(version=1, context_cap=10, intent_quota=1)
    result = fuse(candidates, policy)
    assert [e.chunk_id for e in result.evidence] == ["i1", "j1"]
    assert result.dropped[0].reason == "intent_quota"


def test_context_cap_limits_and_labels_are_sequential():
    candidates = [_candidate(chunk_id=f"c{i}", score=(10 - i) / 10) for i in range(5)]
    result = fuse(candidates, RetrievalPolicy(version=1, context_cap=3))
    assert [e.chunk_id for e in result.evidence] == ["c0", "c1", "c2"]
    assert [e.citation_label for e in result.evidence] == ["[1]", "[2]", "[3]"]
    assert all(e.retained_reason == "retained" for e in result.evidence)
    assert result.dropped == (
        DroppedCandidate(chunk_id="c3", reason="context_cap"),
        DroppedCandidate(chunk_id="c4", reason="context_cap"),
    )
