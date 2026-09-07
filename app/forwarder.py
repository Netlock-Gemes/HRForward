import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError

from .config import Config, Route

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


def _build_source_route_map(
    routes: list[Route],
) -> dict:
    source_route_map = {}

    for route in routes:
        for source in route.sources:
            source_route_map[source] = route

    return source_route_map


def build_client(config: Config) -> Client:
    app = Client(
        "forwarder",
        api_id=config.api_id,
        api_hash=config.api_hash,
        session_string=config.session_string,
        in_memory=True,
    )

    source_route_map = _build_source_route_map(config.routes)

    @app.on_message(
        filters.chat(list(source_route_map.keys()))
        & (filters.video | filters.document)
        & ~filters.outgoing
    )
    async def _on_message(client, message):
        if not message.chat:
            return

        source_id = message.chat.id

        route = source_route_map.get(source_id)

        if route is None:
            log.warning(
                "Received message %s from unconfigured source %s",
                message.id,
                source_id,
            )
            return

        log.info(
            "Message %s received from source %s -> %s destination(s)",
            message.id,
            source_id,
            len(route.destinations),
        )

        tasks = [
            _copy_with_retry(
                message,
                destination_id,
            )
            for destination_id in route.destinations
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        successful = sum(result is True for result in results)

        failed = len(results) - successful

        if failed:
            log.warning(
                "Message %s from source %s: %s succeeded, %s failed",
                message.id,
                source_id,
                successful,
                failed,
            )
        else:
            log.info(
                "Message %s from source %s "
                "forwarded successfully to all %s destination(s)",
                message.id,
                source_id,
                successful,
            )

    return app
