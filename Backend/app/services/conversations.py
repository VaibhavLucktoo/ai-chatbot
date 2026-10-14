"""Opt-in turn memory around the existing asynchronous graph."""

import asyncio
import logging

from app.schemas.chat import ChatResponse
from app.services.conversation_intent import Turn
from app.services.rag import answer_question
from app.storage.conversations import claim_conversation, finish_conversation, release_conversation

logger = logging.getLogger(__name__)


async def answer_conversation(database, db_session, request, key, *, trace=None, assistant=None):
    diagnostic = trace if trace is not None else {}
    claim = await claim_conversation(database, request.conversation_id, key, assistant_id=request.assistant_id)
    try:
        options = {"assistant": assistant} if assistant is not None else {}
        response = await answer_question(db_session, request, trace=diagnostic, history=claim.history, **options)
        # Selection responses are not facts; they do not overwrite the last resolved turn.
        if isinstance(response, ChatResponse):
            scope = diagnostic.get("effective_document_ids", request.document_ids)
            if scope is None and response.sources:
                scope = list(dict.fromkeys(source.document_id for source in response.sources))
            await finish_conversation(database, claim, Turn(
                question=request.question,
                resolved_question=diagnostic.get("resolved_question", request.question),
                answer=response.answer,
                document_ids=tuple(str(identifier) for identifier in scope) if scope is not None else None,
                intent=diagnostic.get("intent", "document_question"), grounded=bool(response.sources),
            ))
        else:
            await release_conversation(database, claim)
        return response
    except BaseException:
        try:
            await asyncio.shield(release_conversation(database, claim))
        except Exception as exc:
            logger.warning("Conversation release failed (%s)", type(exc).__name__)
        raise
