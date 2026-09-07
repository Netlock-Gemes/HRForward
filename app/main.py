import asyncio
import signal

from .config import Config
from .forwarder import build_client
from .logger import setup_logging

log = setup_logging()


async def run() -> None:
    config = Config.load()

    app = build_client(config)

    await app.start()

    me = await app.get_me()

    log.info(
        "Logged in as %s (id=%s)",
        me.first_name,
        me.id,
    )

    log.info(
        "Loaded %s forwarding route(s)",
        len(config.routes),
    )

    for index, route in enumerate(config.routes, start=1):
        log.info(
            "Route #%s: %s source(s) -> %s destination(s)",
            index,
            len(route.sources),
            len(route.destinations),
        )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            stop_event.set,
        )

    await stop_event.wait()

    log.info(
        "Shutdown signal received, stopping..."
    )

    await app.stop()

    log.info("Stopped cleanly")


def main() -> None:
    try:
        asyncio.run(run())

    except SystemExit as e:
        log.error(e)
        raise


if __name__ == "__main__":
    main()