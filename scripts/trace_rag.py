"""Save a private, local trace of the same pipeline used by POST /v1/chat."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import UUID

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.chat import ChatRequest
from app.services.rag import answer_question
from app.storage.db import Database
from run import create_event_loop


async def trace_question(request: ChatRequest) -> dict:
    """Retain intermediate results even when generation/validation fails."""
    trace = {"created_at": datetime.now(timezone.utc).isoformat()}
    database = None
    try:
        settings = get_settings()
        trace.update(
            request=request.model_dump(mode="json"),
            embedding_model=settings.embedding_model,
        )
        database = Database(settings)
        async with database.session() as session:
            await answer_question(session, request, trace=trace)
    except Exception as exc:
        # Exception messages can contain credentials or provider response data.
        trace["error_type"] = type(exc).__name__
    finally:
        if database is not None:
            try:
                await database.close()
            except Exception as exc:
                trace["cleanup_error_type"] = type(exc).__name__
                trace.setdefault("error_type", type(exc).__name__)
    return trace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace exact retrieved passages, messages, model answer, and final response. "
        "Uses your configured model provider. Output contains private document text.",
    )
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--document-id", type=UUID, action="append", dest="document_ids")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        request = ChatRequest(
            question=args.question, top_k=args.top_k, document_ids=args.document_ids,
        )
    except ValidationError:
        parser.error("Use a nonblank question of at most 500 characters, top-k 1–20, "
                     "and at most 20 document IDs.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or Path(".cache/rag-traces") / f"{stamp}.json"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the file before model execution and never overwrite a trace.
        with output.open("x", encoding="utf-8") as target:
            with asyncio.Runner(loop_factory=create_event_loop) as runner:
                trace = runner.run(trace_question(request))
            json.dump(trace, target, indent=2, ensure_ascii=False, default=str)
            target.write("\n")
    except OSError:
        parser.exit(1, "Cannot create trace file; choose a new writable output path.\n")
    print(f"Trace saved: {output.resolve()}")
    if trace.get("error_type"):
        parser.exit(1, f"Trace stopped at {trace['error_type']}; inspect the saved intermediate results.\n")


if __name__ == "__main__":
    main()
