"""Conservative routing: mixed greetings/questions still use document grounding."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.prompts.conversation import FOLLOW_UP_SYSTEM_PROMPT
from app.services.llm import LLMResponseError, generate_llm_response

Intent = Literal["conversation", "document_question", "follow_up", "unsupported"]


@dataclass(frozen=True)
class Turn:
    question: str
    resolved_question: str
    answer: str
    document_ids: tuple[str, ...] | None
    intent: Intent
    grounded: bool = False


GREETING_RESPONSES = {
    "hi": "Hi! How can I help you with your documents today?",
    "hello": "Hello! How can I help you today?",
    "hey": "Hey! What would you like to know about your documents?",
    "hello there": "Hello! How can I help you today?",
    "hi there": "Hi! How can I help you today?",
    "hey there": "Hey! How can I help you today?",
    "hello, how are you": "I'm ready to help, thanks! What can I help you with?",
    "hi, how are you": "I'm ready to help, thanks! What can I help you with?",
    "and you": "I'm ready to help, thanks! What would you like to explore?",
    "good morning": "Good morning! How can I help you today?",
    "good afternoon": "Good afternoon! How can I help you today?",
    "good evening": "Good evening! How can I help you today?",
    "how are you": "I'm ready to help, thanks! What can I help you with?",
    "how are you doing": "I'm ready to help, thanks! What can I help you with?",
    "thanks": "You're welcome! Let me know if you need anything else.",
    "thank you": "You're welcome! Let me know if you need anything else.",
    "thank you very much": "You're welcome! Let me know if you need anything else.",
    "thanks for your help": "You're welcome! Let me know if you need anything else.",
    "thank you for your help": "You're welcome! Let me know if you need anything else.",
    "ok": "Got it. Let me know what you'd like to explore next.",
    "okay": "Got it. Let me know what you'd like to explore next.",
    "got it": "Glad that helped. What would you like to explore next?",
    "bye": "Goodbye! You can come back whenever you need help with your documents.",
    "goodbye": "Goodbye! You can come back whenever you need help with your documents.",
    "who are you": "I'm your document assistant. I can answer questions about uploaded PDFs and show the passages behind an answer.",
    "what can you do": "I can help answer questions about your uploaded PDFs and explain relevant passages. You can manage PDFs in Documents. With conversation memory enabled, you can ask follow-up questions too.",
}
UNSUPPORTED_ANSWER = (
    "I can help with questions about your uploaded PDFs, but I can't browse the "
    "web, take external actions, or create unrelated content. For uploads and "
    "document changes, use the Documents screen."
)
FOLLOW_UP_CLARIFICATION = (
    "Which earlier question, step, or passage do you mean? Please name it or "
    "ask a standalone question so I can check the right document evidence."
)


def conversational_reply(question: str) -> str | None:
    # Only complete, obvious utterances. "Hello, can I take leave?" is NOT a greeting route.
    normalized = re.sub(r"[.!?]+$", "", question.strip().casefold())
    return GREETING_RESPONSES.get(re.sub(r"\s+", " ", normalized))


def detect_intent(question: str) -> Intent:
    if conversational_reply(question) is not None:
        return "conversation"
    if re.search(r"\b(?:this|that|the)\s+(?:document|pdf|file)\b", question, re.IGNORECASE):
        return "document_question"
    if re.match(
        r"^(?:(?:please|can you|could you)\s+)?(?:"
        r"send\s+(?:an?\s+)?(?:email|sms|message)\b|"
        r"(?:browse|search)\s+(?:the\s+)?(?:web|internet)\b|"
        r"(?:book|buy)\s+|"
        r"(?:delete|remove)\s+(?:all\s+)?(?:my\s+)?(?:files|documents)\b|"
        r"(?:write|generate)\s+(?:me\s+)?(?:a\s+)?(?:poem|song|story|joke)\b)",
        question, re.IGNORECASE,
    ):
        return "unsupported"
    if re.match(
        r"^(?:and\b|what about\b|how about\b|tell me more\b|"
        r"what (?:is|was) (?:the )?(?:first|second|third|last|\d+) step\b|"
        r"why(?: is| does| would)?\s+(?:that|it)\b|"
        r"(?:explain|repeat|summari[sz]e|expand)(?:\s+(?:on|the))?\s+"
        r"(?:that|it|this|(?:first|second|third|last|\d+)(?:\s+step)?)\b|"
        r"(?:can|may|should|could)\s+(?:i|we|they)\s+(?:do|use|take|get|apply)\s+(?:it|that|those|them)\b)",
        question, re.IGNORECASE,
    ):
        return "follow_up"
    # Unknown domains may be covered by a PDF. Do not blacklist topics here.
    return "document_question"


class ResolvedFollowUp(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    question: str | None = Field(default=None, min_length=1, max_length=500)
    needs_clarification: bool

    @model_validator(mode="after")
    def coherent_result(self):
        if self.needs_clarification and self.question is not None:
            raise ValueError("Ambiguous reference must not be guessed.")
        if not self.needs_clarification and (self.question is None or not self.question.strip()):
            raise ValueError("A resolved question is required.")
        return self


async def resolve_follow_up(question: str, turn: Turn, *, trace: dict | None = None) -> str | None:
    payload = json.dumps({
        "history": {"question": turn.question, "resolved_question": turn.resolved_question, "answer": turn.answer},
        "latest_question": question,
    }, ensure_ascii=False)
    answer = await generate_llm_response(payload, system_prompt=FOLLOW_UP_SYSTEM_PROMPT, trace=trace)
    try:
        resolved = ResolvedFollowUp.model_validate(json.loads(answer))
    except (ValueError, ValidationError) as exc:
        raise LLMResponseError("The follow-up could not be resolved safely.") from exc
    return None if resolved.needs_clarification else resolved.question.strip()
