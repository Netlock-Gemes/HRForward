import asyncio
import signal

import uvicorn
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Config
from .database import Database
from .forwarder import build_client
from .logger import setup_logging
from .web import create_router

log = setup_logging()


async def run() -> None:
    config = Config.load()

    database = Database(
        config.mongo_uri,
        config.mongo_database,
    )

    await database.connect()

    log.info("Connected to MongoDB")

    telegram_app = build_client(
        config,
        database,
    )

    await telegram_app.start()

    me = await telegram_app.get_me()

    log.info(
        "Logged in as %s (id=%s)",
        me.first_name,
        me.id,
    )

    web_app = FastAPI(
        title="Telegram Forwarder",
    )

    web_app.add_middleware(
        SessionMiddleware,
        secret_key=config.secret_key,
        max_age=60 * 60 * 24 * 7,
    )

    web_app.mount(
        "/static",
        StaticFiles(directory="static"),
        name="static",
    )

    web_app.state.templates = Jinja2Templates(
        directory="templates"
    )

    web_app.include_router(
        create_router(
            config,
            database,
        )
    )

    server_config = uvicorn.Config(
        web_app,
        host=config.host,
        port=config.port,
        log_level="info",
    )

    server = uvicorn.Server(server_config)

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            stop_event.set,
        )

    web_task = asyncio.create_task(
        server.serve()
    )

    log.info(
        "Web dashboard running on %s:%s",
        config.host,
        config.port,
    )

    await stop_event.wait()

    log.info(
        "Shutdown signal received, stopping..."
    )

    server.should_exit = True

    await web_task

    await telegram_app.stop()
    await database.close()

    log.info("Stopped cleanly")


def main() -> None:
    try:
        asyncio.run(run())

    except SystemExit as e:
        log.error(e)
        raise


if __name__ == "__main__":
    main()