"""Workspace 隔离域检查（ADR 0003；CONTEXT：Workspace / Workspace Member）。"""

from medicalrag_core.identity.workspace import (
    Role,
    UserMemberships,
    Workspace,
    WorkspaceMember,
)


def _memberships(user_id: str = "u-1") -> UserMemberships:
    return UserMemberships(
        user_id=user_id,
        memberships=(
            WorkspaceMember("u-1", "ws-a", Role.MEMBER),
            WorkspaceMember("u-1", "ws-b", Role.OPERATOR),
        ),
    )


def test_membership_scope_and_roles():
    memberships = _memberships()
    assert memberships.workspaces() == ("ws-a", "ws-b")
    assert memberships.is_platform_operator()


def test_member_only_user_is_not_operator():
    memberships = UserMemberships(
        user_id="u-2", memberships=(WorkspaceMember("u-2", "ws-a", Role.MEMBER),)
    )
    assert not memberships.is_platform_operator()


def test_workspace_entity_is_frozen_and_named():
    workspace = Workspace(id="ws-1", name="第一人民医院心内科")
    assert workspace.name == "第一人民医院心内科"
    assert workspace.id == "ws-1"
