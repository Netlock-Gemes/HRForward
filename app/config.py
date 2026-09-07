import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from dotenv import load_dotenv

load_dotenv()

ChatId = Union[int, str]


def _parse_chat_id(value: str) -> ChatId:
    value = value.strip()

    if not value:
        raise ValueError("Chat ID cannot be empty")

    return int(value) if value.lstrip("-").isdigit() else value


@dataclass(frozen=True)
class Route:
    sources: list[ChatId]
    destinations: list[ChatId]


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session_string: str
    routes: list[Route]

    @classmethod
    def load(cls) -> "Config":
        required = (
            "API_ID",
            "API_HASH",
            "SESSION_STRING",
            "ROUTES_FILE",
        )

        missing = [
            key
            for key in required
            if not os.environ.get(key, "").strip()
        ]

        if missing:
            raise SystemExit(
                "Missing required environment variable(s): "
                + ", ".join(missing)
            )

        # API ID
        try:
            api_id = int(os.environ["API_ID"])
        except ValueError:
            raise SystemExit("API_ID must be an integer")

        # Routes file
        routes_file = Path(os.environ["ROUTES_FILE"]).expanduser()

        if not routes_file.is_file():
            raise SystemExit(
                f"Routes file not found: {routes_file}"
            )

        try:
            with routes_file.open("r", encoding="utf-8") as file:
                routes_data = json.load(file)
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"Invalid JSON in routes file: {e}"
            )
        except OSError as e:
            raise SystemExit(
                f"Unable to read routes file: {e}"
            )

        if not isinstance(routes_data, list):
            raise SystemExit(
                "Routes file must contain a JSON array"
            )

        routes: list[Route] = []

        for index, route_data in enumerate(routes_data, start=1):
            if not isinstance(route_data, dict):
                raise SystemExit(
                    f"Route #{index} must be an object"
                )

            if "sources" not in route_data:
                raise SystemExit(
                    f"Route #{index} is missing 'sources'"
                )

            if "destinations" not in route_data:
                raise SystemExit(
                    f"Route #{index} is missing 'destinations'"
                )

            raw_sources = route_data["sources"]
            raw_destinations = route_data["destinations"]

            if not isinstance(raw_sources, list) or not raw_sources:
                raise SystemExit(
                    f"Route #{index} must contain at least one source"
                )

            if (
                not isinstance(raw_destinations, list)
                or not raw_destinations
            ):
                raise SystemExit(
                    f"Route #{index} must contain at least one destination"
                )

            try:
                sources = [
                    _parse_chat_id(str(value))
                    for value in raw_sources
                ]

                destinations = [
                    _parse_chat_id(str(value))
                    for value in raw_destinations
                ]
            except ValueError as e:
                raise SystemExit(
                    f"Invalid chat ID in route #{index}: {e}"
                )

            routes.append(
                Route(
                    sources=sources,
                    destinations=destinations,
                )
            )

        if not routes:
            raise SystemExit(
                "Routes file must contain at least one route"
            )

        # Make sure a source does not belong to multiple routes.
        source_to_route: dict[ChatId, int] = {}

        for route_index, route in enumerate(routes, start=1):
            for source in route.sources:
                if source in source_to_route:
                    previous_route = source_to_route[source]

                    raise SystemExit(
                        f"Source {source} is configured in both "
                        f"route #{previous_route} and route #{route_index}. "
                        "A source can belong to only one route."
                    )

                source_to_route[source] = route_index

        return cls(
            api_id=api_id,
            api_hash=os.environ["API_HASH"].strip(),
            session_string=os.environ["SESSION_STRING"].strip(),
            routes=routes,
        )