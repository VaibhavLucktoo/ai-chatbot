import asyncio
import argparse
import sys
from copy import deepcopy

import uvicorn


def create_event_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    return loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local console or isolated HTTPS widget gateway.")
    parser.add_argument("--widget-gateway", action="store_true", help="Serve only website-widget routes on loopback port 8001 behind an HTTPS proxy.")
    args = parser.parse_args()
    log_config = deepcopy(uvicorn.config.LOGGING_CONFIG)
    log_config["loggers"]["app"] = {"handlers": ["default"], "level": "INFO", "propagate": False}
    config = uvicorn.Config(
        app="app.widget_gateway:create_widget_gateway" if args.widget_gateway else "app.main:app",
        factory=args.widget_gateway,
        host="127.0.0.1",
        port=8001 if args.widget_gateway else 8000,
        log_level="info",
        log_config=log_config,
        proxy_headers=False,
    )
    server = uvicorn.Server(config)

    # Own the event loop explicitly, avoiding Uvicorn's automatic selection.
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(server.serve())


if __name__ == "__main__":
    main()
