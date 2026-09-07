import os
from dataclasses import dataclass
from typing import Union

from dotenv import load_dotenv

load_dotenv()

ChatId = Union[int, str]


def parse_chat_id(value: str) -> ChatId:
    value = value.strip()

    if not value:
        raise ValueError("Chat ID cannot be empty")

    return int(value) if value.lstrip("-").isdigit() else value


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session_string: str

    mongo_uri: str
    mongo_database: str

    admin_username: str
    admin_password: str

    host: str
    port: int
    secret_key: str

    @classmethod
    def load(cls) -> "Config":
        required = (
            "API_ID",
            "API_HASH",
            "SESSION_STRING",
            "MONGO_URI",
            "MONGO_DATABASE",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "SECRET_KEY",
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

        try:
            api_id = int(os.environ["API_ID"])
        except ValueError:
            raise SystemExit("API_ID must be an integer")

        try:
            port = int(os.environ.get("PORT", "8000"))
        except ValueError:
            raise SystemExit("PORT must be an integer")

        return cls(
            api_id=api_id,
            api_hash=os.environ["API_HASH"].strip(),
            session_string=os.environ["SESSION_STRING"].strip(),
            mongo_uri=os.environ["MONGO_URI"].strip(),
            mongo_database=os.environ["MONGO_DATABASE"].strip(),
            admin_username=os.environ["ADMIN_USERNAME"].strip(),
            admin_password=os.environ["ADMIN_PASSWORD"],
            host=os.environ.get("HOST", "0.0.0.0"),
            port=port,
            secret_key=os.environ["SECRET_KEY"].strip(),
        )