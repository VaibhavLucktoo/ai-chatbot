"""Async LangChain adapter for the application's validated chat transport."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class CompatibleChatModel(BaseChatModel):
    """Expose the existing HTTP contract as an async LangChain Runnable.

    The transport owns configuration, deadlines, and response validation.
    Streaming, tools, synchronous calls, and stop sequences are unsupported.
    Request traces are invocation arguments, never shared model state.
    """

    transport: Callable[..., Awaitable[str | tuple[str, dict]]] = Field(exclude=True, repr=False)
    model_name: str = "configured-model"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": self.model_name}

    @property
    def _llm_type(self) -> str:
        return "validated-openai-compatible"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("Use ainvoke() for this asynchronous chat model.")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if stop is not None:
            raise ValueError("Stop sequences are not supported.")
        trace = kwargs.pop("trace", None)
        if kwargs:
            raise ValueError("Unsupported chat generation options.")
        payload = []
        for message in messages:
            if not isinstance(message.content, str):
                raise ValueError("Only text chat messages are supported.")
            if isinstance(message, SystemMessage):
                role = "system"
            elif isinstance(message, HumanMessage):
                role = "user"
            else:
                raise ValueError("Only system and user messages are supported.")
            payload.append({"role": role, "content": message.content})
        answer = await self.transport(payload, trace=trace)
        metadata = {}
        if isinstance(answer, tuple):
            answer, metadata = answer
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=answer, response_metadata=metadata,
        ))])
