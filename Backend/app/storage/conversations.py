"""Short fenced database claims; never hold a connection during generation."""

import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.services.conversation_intent import Turn
from app.storage.models import ChatConversation, Assistant


class ConversationAccessError(RuntimeError):
    pass


class ConversationBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversationClaim:
    id: UUID
    attempt_id: UUID
    history: tuple[Turn, ...]


def bounded_history(turns: list[Turn], *, max_turns: int, max_bytes: int) -> list[dict]:
    """Keep complete recent turns. Never summarize model claims into evidence."""
    result = []
    for turn in reversed(turns[-max_turns:]):
        item = asdict(turn)
        trial = [item, *result]
        if len(json.dumps(trial, ensure_ascii=False).encode("utf-8")) > max_bytes:
            break
        result = trial
    return result


async def claim_conversation(database, conversation_id: UUID, key: str | None,
                             *, assistant_id: UUID | None = None) -> ConversationClaim:
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32,128}", key):
        raise ConversationAccessError("A valid conversation key is required. Start a new chat.")
    digest = sha256(key.encode("ascii")).hexdigest()
    settings = database.settings
    attempt = uuid4()
    async with database.transaction() as connection:
        if assistant_id is not None:
            # Serialize new claims with assistant deletion; release before generation.
            available = await connection.scalar(select(Assistant.id).where(
                Assistant.id == assistant_id, Assistant.active.is_(True)).with_for_update(read=True))
            if available is None:
                raise ConversationAccessError("Assistant is unavailable. Refresh the assistant list.")
        # Expired session memory is private data; prune a bounded batch, not documents.
        expired = select(ChatConversation.id).where(
            ChatConversation.expires_at <= func.now(),
            (ChatConversation.attempt_id.is_(None)) | (ChatConversation.lease_expires_at <= func.now()),
        ).order_by(ChatConversation.expires_at).limit(100)
        await connection.execute(delete(ChatConversation).where(ChatConversation.id.in_(expired)))
        # A target outside the bounded cleanup batch must never retain expired history.
        await connection.execute(delete(ChatConversation).where(
            ChatConversation.id == conversation_id, ChatConversation.expires_at <= func.now(),
            (ChatConversation.attempt_id.is_(None)) | (ChatConversation.lease_expires_at <= func.now()),
        ))
        await connection.execute(insert(ChatConversation).values(
            id=conversation_id, owner_key_hash=digest, history=[], assistant_id=assistant_id,
            expires_at=func.now() + timedelta(seconds=settings.conversation_ttl_seconds),
        ).on_conflict_do_nothing(index_elements=[ChatConversation.id]))
        row = (await connection.execute(select(
            ChatConversation.owner_key_hash, ChatConversation.history, ChatConversation.assistant_id,
        ).where(ChatConversation.id == conversation_id))).one()
        if not secrets.compare_digest(row.owner_key_hash, digest) or row.assistant_id != assistant_id:
            raise ConversationAccessError("Conversation is unavailable. Start a new chat.")
        acquired = await connection.execute(update(ChatConversation).where(
            ChatConversation.id == conversation_id, ChatConversation.owner_key_hash == digest,
            (ChatConversation.attempt_id.is_(None)) | (ChatConversation.lease_expires_at <= func.now()),
        ).values(attempt_id=attempt,
                 lease_expires_at=func.now() + timedelta(seconds=settings.chat_timeout_seconds + 30)))
        if acquired.rowcount != 1:
            raise ConversationBusyError("Another turn in this conversation is processing. Retry shortly.")
        # Read after acquiring ownership so a concurrently completed turn is visible.
        history = await connection.scalar(select(ChatConversation.history).where(ChatConversation.id == conversation_id))
    turns = tuple(Turn(**{**item, "document_ids": tuple(item["document_ids"]) if item["document_ids"] is not None else None}) for item in history)
    return ConversationClaim(conversation_id, attempt, turns)


async def finish_conversation(database, claim: ConversationClaim, turn: Turn) -> None:
    settings = database.settings
    history = bounded_history([*claim.history, turn], max_turns=settings.conversation_max_turns,
                              max_bytes=settings.conversation_max_history_bytes)
    async with database.transaction() as connection:
        saved = await connection.execute(update(ChatConversation).where(
            ChatConversation.id == claim.id, ChatConversation.attempt_id == claim.attempt_id,
            ChatConversation.lease_expires_at > func.now(),
        ).values(history=history, attempt_id=None, lease_expires_at=None,
                 expires_at=func.now() + timedelta(seconds=settings.conversation_ttl_seconds)))
        if saved.rowcount != 1:
            raise ConversationBusyError("Conversation ownership expired. Retry the question.")


async def release_conversation(database, claim: ConversationClaim) -> None:
    async with database.transaction() as connection:
        await connection.execute(update(ChatConversation).where(
            ChatConversation.id == claim.id, ChatConversation.attempt_id == claim.attempt_id,
        ).values(attempt_id=None, lease_expires_at=None))
