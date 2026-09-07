from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


class Database:
    def __init__(self, uri: str, database_name: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[database_name]
        self.routes = self.db["routes"]

    async def connect(self) -> None:
        await self.client.admin.command("ping")
        await self.routes.create_index(
            "sources",
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

        return route

    async def create_route(
        self,
        name: str,
        sources: list[int | str],
        destinations: list[int | str],
        delay_seconds: int,
    ) -> str:
        now = datetime.now(timezone.utc)

        document = {
            "name": name,
            "sources": sources,
            "destinations": destinations,
            "delay_seconds": delay_seconds,
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
    ) -> bool:
        result = await self.routes.update_one(
            {"_id": ObjectId(route_id)},
            {
                "$set": {
                    "name": name,
                    "sources": sources,
                    "destinations": destinations,
                    "delay_seconds": delay_seconds,
                    "enabled": enabled,
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