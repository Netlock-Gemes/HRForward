import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError

from .config import Config
from .database import Database


log = logging.getLogger("tg-forwarder")

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


async def _copy_with_retry(
    message,
    destination_id,
) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await message.copy(destination_id)

            log.info(
                "Copied message %s from %s -> %s",
                message.id,
                message.chat.id,
                destination_id,
            )

            return True

        except FloodWait as e:
            log.warning(
                "FloodWait: sleeping %ss (attempt %s/%s) for destination %s",
                e.value,
                attempt,
                MAX_RETRIES,
                destination_id,
            )

            await asyncio.sleep(e.value)

        except RPCError as e:
            log.error(
                "RPC error on attempt %s/%s for message %s -> %s: %s",
                attempt,
                MAX_RETRIES,
                message.id,
                destination_id,
                e,
            )

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        except Exception:
            log.exception(
                "Unexpected error copying message %s -> %s",
                message.id,
                destination_id,
            )

            return False

    log.error(
        "Giving up on message %s -> %s after %s attempts",
        message.id,
        destination_id,
        MAX_RETRIES,
    )

    return False


async def _forward_message(
    message,
    destinations,
    delay_seconds: int,
) -> None:
    if delay_seconds > 0:
        log.info(
            "Message %s: waiting %s second(s) before forwarding",
            message.id,
            delay_seconds,
        )

        await asyncio.sleep(delay_seconds)

    tasks = [
        _copy_with_retry(
            message,
            destination_id,
        )
        for destination_id in destinations
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    successful = sum(result is True for result in results)

    failed = len(results) - successful

    if failed:
        log.warning(
            "Message %s: %s succeeded, %s failed",
            message.id,
            successful,
            failed,
        )
    else:
        log.info(
            "Message %s forwarded successfully to all %s destination(s)",
            message.id,
            successful,
        )


def build_client(
    config: Config,
    database: Database,
) -> Client:
    app = Client(
        "forwarder",
        api_id=config.api_id,
        api_hash=config.api_hash,
        session_string=config.session_string,
        in_memory=True,
    )

    @app.on_message(filters.video | filters.document)
    async def _on_message(
        client,
        message,
    ):
        if not message.chat:
            return

        source_id = message.chat.id

        route = await database.get_route_for_source(source_id)

        if route is None:
            return

        destinations = route["destinations"]
        delay_seconds = route.get(
            "delay_seconds",
            0,
        )

        log.info(
            "Message %s from source %s matched route '%s' (delay: %ss)",
            message.id,
            source_id,
            route["name"],
            delay_seconds,
        )

        # Each incoming message gets its own independent
        # forwarding task and timer.
        asyncio.create_task(
            _forward_message(
                message,
                destinations,
                delay_seconds,
            )
        )

    return app
