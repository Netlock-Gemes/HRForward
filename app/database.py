from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


# Defaults for routes created before caption settings existed.
CAPTION_DEFAULTS = {
    "caption_mode": "original",
    "clean_filename": False,
    "remove_texts": [],
    "keep_extension": False,
}

# Name of the old unique index that only covered "sources", which
# incorrectly blocked multiple routes from sharing the same source.
_LEGACY_SOURCES_INDEX = "sources_1"


def _build_source_destination_pairs(
    sources: list[int | str],
    destinations: list[int | str],
) -> list[str]:
    """Flatten sources/destinations into "source::destination" pairs.

    A unique multikey index on this single array field enforces that no
    two routes share an identical source -> destination pair, while still
    allowing the same source (or destination) to appear across routes.
    A compound index directly on ``sources``/``destinations`` isn't
    possible here since MongoDB doesn't allow indexing two array fields
    together ("parallel arrays") - both fields hold lists.
    """

    return sorted(
        {
            f"{source}::{destination}"
            for source in sources
            for destination in destinations
        }
    )


class Database:
    def __init__(self, uri: str, database_name: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[database_name]
        self.routes = self.db["routes"]

    async def connect(self) -> None:
        await self.client.admin.command("ping")

        # Backfill routes that predate source_destination_pairs so the
        # unique index below can be built without failing on documents
        # that are missing the field. No existing route data is changed
        # beyond adding this derived field.
        async for route in self.routes.find(
            {"source_destination_pairs": {"$exists": False}}
        ):
            await self.routes.update_one(
                {"_id": route["_id"]},
                {
                    "$set": {
                        "source_destination_pairs": (
                            _build_source_destination_pairs(
                                route.get("sources", []),
                                route.get("destinations", []),
                            )
                        ),
                    }
                },
            )

        # Replace the old sources-only unique index (which blocked any
        # two routes from sharing a source at all) with a uniqueness
        # constraint on each individual source -> destination pair.
        existing_indexes = await self.routes.index_information()

        if _LEGACY_SOURCES_INDEX in existing_indexes:
            await self.routes.drop_index(_LEGACY_SOURCES_INDEX)

        await self.routes.create_index(
            "source_destination_pairs",
            unique=True,
        )

    async def close(self) -> None:
        self.client.close()

    async def get_routes(self) -> list[dict[str, Any]]:
        cursor = self.routes.find().sort("created_at", 1)
        routes = []

        async for route in cursor:
            route["_id"] = str(route["_id"])

            # Support routes created before delay_seconds was added.
            route.setdefault("delay_seconds", 0)

            # Support routes created before caption settings were added.
            for key, value in CAPTION_DEFAULTS.items():
                route.setdefault(key, value)

            routes.append(route)

        return routes

    async def get_route_for_source(
        self,
        source_id: int,
    ) -> dict[str, Any] | None:
        route = await self.routes.find_one(
            {
                "sources": source_id,
                "enabled": True,
            }
        )

        if route is not None:
            # Support routes created before delay_seconds was added.
            route.setdefault("delay_seconds", 0)

            # Support routes created before caption settings were added.
            for key, value in CAPTION_DEFAULTS.items():
                route.setdefault(key, value)

        return route

    async def create_route(
        self,
        name: str,
        sources: list[int | str],
        destinations: list[int | str],
        delay_seconds: int,
        caption_mode: str = CAPTION_DEFAULTS["caption_mode"],
        clean_filename: bool = CAPTION_DEFAULTS["clean_filename"],
        remove_texts: list[str] = CAPTION_DEFAULTS["remove_texts"],
        keep_extension: bool = CAPTION_DEFAULTS["keep_extension"],
    ) -> str:
        now = datetime.now(timezone.utc)

        document = {
            "name": name,
            "sources": sources,
            "destinations": destinations,
            "source_destination_pairs": _build_source_destination_pairs(
                sources,
                destinations,
            ),
            "delay_seconds": delay_seconds,
            "caption_mode": caption_mode,
            "clean_filename": clean_filename,
            "remove_texts": remove_texts,
            "keep_extension": keep_extension,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.routes.insert_one(document)

        return str(result.inserted_id)

    async def update_route(
        self,
        route_id: str,
        name: str,
        sources: list[int | str],
        destinations: list[int | str],
        delay_seconds: int,
        enabled: bool,
        caption_mode: str = CAPTION_DEFAULTS["caption_mode"],
        clean_filename: bool = CAPTION_DEFAULTS["clean_filename"],
        remove_texts: list[str] = CAPTION_DEFAULTS["remove_texts"],
        keep_extension: bool = CAPTION_DEFAULTS["keep_extension"],
    ) -> bool:
        result = await self.routes.update_one(
            {"_id": ObjectId(route_id)},
            {
                "$set": {
                    "name": name,
                    "sources": sources,
                    "destinations": destinations,
                    "source_destination_pairs": _build_source_destination_pairs(
                        sources,
                        destinations,
                    ),
                    "delay_seconds": delay_seconds,
                    "enabled": enabled,
                    "caption_mode": caption_mode,
                    "clean_filename": clean_filename,
                    "remove_text": remove_texts,
                    "keep_extension": keep_extension,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        return result.modified_count > 0

    async def delete_route(
        self,
        route_id: str,
    ) -> bool:
        result = await self.routes.delete_one(
            {"_id": ObjectId(route_id)}
        )

        return result.deleted_count > 0