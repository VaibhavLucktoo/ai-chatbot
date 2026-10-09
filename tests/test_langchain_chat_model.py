"""Verify the model's Runnable contract without an external provider."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

from app.providers.chat_model import CompatibleChatModel
from app.services.llm import LLMRateLimitError


class LangChainChatModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_composes_with_parser_and_emits_callbacks(self):
        events = []

        class Handler(AsyncCallbackHandler):
            async def on_chat_model_start(self, serialized, messages, **kwargs):
                events.append("start")

            async def on_llm_end(self, response, **kwargs):
                events.append("end")

        transport = AsyncMock(return_value="Grounded answer")
        model = CompatibleChatModel(transport=transport, cache=False)
        result = await (model | StrOutputParser()).ainvoke(
            [SystemMessage(content="Use sources"), HumanMessage(content="Question")],
            config={"callbacks": [Handler()]},
        )
        self.assertEqual(result, "Grounded answer")
        self.assertEqual(events, ["start", "end"])
        transport.assert_awaited_once_with([
            {"role": "system", "content": "Use sources"},
            {"role": "user", "content": "Question"},
        ], trace=None)

    async def test_concurrent_invocations_keep_traces_separate(self):
        async def transport(messages, *, trace):
            await asyncio.sleep(0)
            trace["question"] = messages[0]["content"]
            return trace["question"]

        model = CompatibleChatModel(transport=transport, cache=False)
        first, second = {}, {}
        answers = await asyncio.gather(
            model.ainvoke("first", trace=first), model.ainvoke("second", trace=second),
        )
        self.assertEqual([answer.content for answer in answers], ["first", "second"])
        self.assertEqual(first, {"question": "first"})
        self.assertEqual(second, {"question": "second"})

    async def test_provider_errors_propagate_without_retry(self):
        transport = AsyncMock(side_effect=LLMRateLimitError())
        with self.assertRaises(LLMRateLimitError):
            await CompatibleChatModel(transport=transport, cache=False).ainvoke("Question")
        self.assertEqual(transport.await_count, 1)

    async def test_unsupported_inputs_do_not_call_provider(self):
        transport = AsyncMock()
        model = CompatibleChatModel(transport=transport, cache=False)
        for messages, options in [
            ([AIMessage(content="Answer")], {}),
            ([HumanMessage(content=[{"type": "text", "text": "Question"}])], {}),
            ([HumanMessage(content="Question")], {"stop": ["END"]}),
            ([HumanMessage(content="Question")], {"temperature": 1}),
        ]:
            with self.subTest(messages=messages, options=options), self.assertRaises(ValueError):
                await model.ainvoke(messages, **options)
        transport.assert_not_awaited()
