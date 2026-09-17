"""反馈 / Conversation / Outbox 领域实体检查（契约形状对齐运营后台）。"""

from medicalrag_core.records import Conversation, Feedback, FeedbackValue, OutboxMessage


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


def test_conversation_entity_shape():
    conversation = Conversation(id="conv-1", user_id="u-1", workspace_id="ws-1", title="高血压")
    assert conversation.workspace_id == "ws-1"
    assert conversation.title == "高血压"


def test_outbox_message_carries_attempts_and_timestamps():
    message = OutboxMessage(
        id="ob-1",
        aggregate_type="ingestion_run",
        aggregate_id="run-1",
        event_type="ingestion.stage",
        payload={"stage": "indexing"},
    )
    assert message.attempts == 0
    assert message.processed_at is None
