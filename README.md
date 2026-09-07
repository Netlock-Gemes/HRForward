# tg-forwarder

Minimal headless Telegram forwarder built with PyroFork.

```
SOURCE_IDS → DESTINATION_ID
```

Monitors one or more sources (channels, groups, users, bots) and copies every new,
incoming message to a single destination using Telegram's `copy_message`, so the
destination message has no "Forwarded from" header. Messages sent by the logged-in
account itself are ignored.

## Project structure

```
app/
  config.py    # loads and validates .env into a Config object
  logger.py    # logging setup
  forwarder.py # Pyrogram client, message handler, FloodWait/retry logic
  main.py      # startup, run loop, graceful shutdown
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

## Setup

1. Copy `.env.example` to `.env` and fill in your values:

   - `API_ID`, `API_HASH` — from https://my.telegram.org
   - `SESSION_STRING` — a Pyrogram/PyroFork **user** session string
   - `SOURCE_IDS` — comma-separated chat IDs/usernames to watch
   - `DESTINATION_ID` — chat ID/username to forward messages to

2. Run with Docker Compose (recommended):

   ```bash
   docker compose up -d
   ```

   View logs:

   ```bash
   docker compose logs -f
   ```

   Stop:

   ```bash
   docker compose down
   ```

### Run locally without Docker

```bash
pip install -r requirements.txt
python -m app.main
```

## Behavior

- Validates all required environment variables at startup and exits with a clear
  error if anything is missing or malformed.
- Listens for new, incoming messages in every configured source (ignoring messages
  sent by the logged-in account) and copies each to the destination.
- On `FloodWait`, sleeps for the required duration and retries.
- On other Telegram RPC errors, retries with a short backoff (up to 3 attempts)
  before giving up on that message and moving on.
- Logs startup info, each forwarded message, and any errors to stdout.
- Shuts down cleanly on `SIGINT`/`SIGTERM`.
