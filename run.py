import asyncio
import sys

import uvicorn


def create_event_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    return loop


def main() -> None:
    config = uvicorn.Config(
        app="app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Own the event loop explicitly, avoiding Uvicorn's automatic selection.
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(server.serve())


if __name__ == "__main__":
    main()