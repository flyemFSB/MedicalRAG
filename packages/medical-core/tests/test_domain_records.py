"""反馈 / Conversation / Outbox / 审计领域实体检查（契约形状对齐运营后台）。"""

from medicalrag_core.audit import AuditEvent
from medicalrag_core.conversation import Conversation, ConversationRef
from medicalrag_core.feedback import Feedback, FeedbackValue
from medicalrag_core.outbox import OutboxMessage


def test_feedback_entity_shape():
    feedback = Feedback(
        id="fb-1",
        message_id="msg-1",
        conversation_id="conv-1",
        user_id="u-1",
        workspace_id="ws-1",
        value=FeedbackValue.DISLIKE,
        comment="未直接说明注意事项",
    )
    assert feedback.value is FeedbackValue.DISLIKE
    assert feedback.comment == "未直接说明注意事项"


def test_conversation_and_thread_mapping():
    conversation = Conversation(id="conv-1", user_id="u-1", workspace_id="ws-1", title="高血压")
    ref = ConversationRef(conversation_id="conv-1", thread_id="thread-1")
    assert conversation.workspace_id == "ws-1"
    assert ref.thread_id == "thread-1"


def test_outbox_message_job_id_is_stable():
    message = OutboxMessage(
        id="ob-1",
        aggregate_type="ingestion_run",
        aggregate_id="run-1",
        event_type="stage_completed",
        payload={"stage": "indexing"},
    )
    assert message.job_id == "outbox:ob-1"


def test_audit_event_requires_safe_detail_only():
    event = AuditEvent(
        id="au-1",
        actor_user_id="u-1",
        actor_email="ops@clinic.example",
        workspace_id="ws-1",
        action="创建",
        entity_type="知识库",
        entity_name="常用药物与相互作用",
        detail="新建知识库并上传文档",
    )
    assert event.actor_email == "ops@clinic.example"
    assert event.entity_type == "知识库"
