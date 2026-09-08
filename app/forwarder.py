import asyncio
import logging
import os

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError

from .config import Config
from .database import Database


log = logging.getLogger("tg-forwarder")

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def _get_message_filename(message) -> str | None:
    if message.document and message.document.file_name:
        return message.document.file_name

    if message.video and message.video.file_name:
        return message.video.file_name

    return None


def _strip_text_case_insensitive(text: str, remove_text: str) -> str:
    if not remove_text:
        return text

    lower_text = text.lower()
    lower_remove = remove_text.lower()

    pieces = []
    start = 0
    index = lower_text.find(lower_remove, start)

    while index != -1:
        pieces.append(text[start:index])
        start = index + len(remove_text)
        index = lower_text.find(lower_remove, start)

    pieces.append(text[start:])

    return "".join(pieces)


def _clean_filename_text(text: str) -> str:
    # Replace separators with spaces, then collapse/trim whitespace.
    # Hyphens and other meaningful characters are left untouched.
    cleaned = text.replace(".", " ").replace("_", " ")
    return " ".join(cleaned.split())


def _strip_extension(text: str, original_extension: str) -> str:
    if not original_extension:
        return text

    extension_no_dot = original_extension[1:]
    lower_text = text.lower()

    if extension_no_dot and lower_text.endswith(extension_no_dot.lower()):
        # Cleaning may have already turned the leading "." into a space
        # (or removed it), so match on the extension text itself and trim
        # any leftover separator.
        text = text[: len(text) - len(extension_no_dot)]

        return text.rstrip(" .")

    if lower_text.endswith(original_extension.lower()):
        return text[: len(text) - len(original_extension)]

    return text


def _build_filename_caption(filename: str, route) -> str:
    remove_text = route.get("remove_text") or ""
    clean_filename = route.get("clean_filename", False)
    keep_extension = route.get("keep_extension", False)

    stem, extension = os.path.splitext(filename)

    stem = _strip_text_case_insensitive(stem, remove_text)

    if clean_filename:
        stem = _clean_filename_text(stem)

    if keep_extension:
        return f"{stem.strip()}{extension}"

    return stem.strip()


def _build_caption(
    message,
    route,
) -> str | None:
    """Return the caption to send with the copied media.

    Returns ``None`` when the original caption should be preserved
    (i.e. no ``caption`` argument should be passed to ``message.copy``),
    keeping the existing behavior untouched for that case.
    """

    caption_mode = route.get("caption_mode", "original")

    if caption_mode == "none":
        return ""

    if caption_mode == "filename":
        filename = _get_message_filename(message)

        if not filename:
            # No filename to build a caption from; fall back to the
            # existing behavior instead of sending an empty caption.
            return None

        return _build_filename_caption(filename, route)

    # "original" (and any unrecognized/legacy value) keeps existing behavior.
    return None


async def _copy_with_retry(
    message,
    destination_id,
    caption: str | None = None,
) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if caption is None:
                await message.copy(destination_id)
            else:
                await message.copy(destination_id, caption=caption)

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
    route,
) -> None:
    if delay_seconds > 0:
        log.info(
            "Message %s: waiting %s second(s) before forwarding",
            message.id,
            delay_seconds,
        )

        await asyncio.sleep(delay_seconds)

    # Caption is generated once per message, not once per destination.
    caption = _build_caption(message, route)

    tasks = [
        _copy_with_retry(
            message,
            destination_id,
            caption,
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
                route,
            )
        )

    return app
