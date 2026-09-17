"""动态意图树检查（ADR 0044）。"""

import pytest

from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentResolution, IntentTree, IntentTreeError, ScoredIntent
from medicalrag_core.safety.policy import RiskClass


def _node(node_id: str, **overrides) -> IntentNode:
    defaults = {
        "id": node_id,
        "level": IntentLevel.TOPIC,
        "kind": IntentKind.KNOWLEDGE,
        "name": node_id,
    }
    defaults.update(overrides)
    return IntentNode(**defaults)


def _tree() -> IntentTree:
    """一个三层的意图树（含禁用叶子、非叶子、SYSTEM 节点）。"""
    return IntentTree(
        [
            _node("medical", level=IntentLevel.DOMAIN),
            _node("disease", level=IntentLevel.CATEGORY, parent_id="medical"),
            _node("disease-info", parent_id="disease"),
            _node(
                "disease-treatment",
                parent_id="disease",
                safety_class=RiskClass.TREATMENT,
            ),
            _node("system", level=IntentLevel.CATEGORY, parent_id="medical"),
            _node("system-greet", parent_id="system", kind=IntentKind.SYSTEM),
            _node("system-disabled", parent_id="system", enabled=False),
            _node("middle", parent_id="medical"),
            _node("leaf-x", parent_id="middle"),
        ]
    )


def test_eligible_leaves_excludes_disabled_and_non_leaves():
    tree = _tree()
    ids = [n.id for n in tree.eligible_leaves()]
    assert sorted(ids) == ["disease-info", "disease-treatment", "leaf-x", "system-greet"]


def test_duplicate_node_id_raises():
    with pytest.raises(IntentTreeError):
        IntentTree([_node("a"), _node("a")])


def test_unknown_parent_raises():
    with pytest.raises(IntentTreeError):
        IntentTree([_node("a", parent_id="ghost")])


def test_cycle_raises():
    with pytest.raises(IntentTreeError):
        IntentTree([_node("a", parent_id="b"), _node("b", parent_id="a")])


def test_resolve_whitelists_known_and_drops_unknown():
    tree = _tree()
    result = tree.resolve(
        [
            ScoredIntent("disease-info", 0.9),
            ScoredIntent("ghost", 0.95),
            ScoredIntent("system-disabled", 0.8),
        ]
    )
    assert [s.node_id for s in result.known] == ["disease-info"]
    assert [n.id for n in result.nodes] == ["disease-info"]


def test_resolve_sorts_by_score_desc_with_stable_tie_break():
    tree = _tree()
    result = tree.resolve(
        [
            ScoredIntent("disease-treatment", 0.5),
            ScoredIntent("disease-info", 0.7),
            ScoredIntent("system-greet", 0.7),
        ]
    )
    assert [s.node_id for s in result.known] == [
        "disease-info",
        "system-greet",
        "disease-treatment",
    ]


def test_resolve_applies_threshold():
    tree = _tree()
    result = tree.resolve(
        [ScoredIntent("disease-info", 0.6), ScoredIntent("system-greet", 0.4)],
        threshold=0.5,
    )
    assert [s.node_id for s in result.known] == ["disease-info"]


def test_resolve_empty_candidates():
    tree = _tree()
    result = tree.resolve([])
    assert result == IntentResolution((), ())
