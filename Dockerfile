FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim

COPY --from=builder /venv /venv

ENV PATH="/venv/bin:$PATH"

WORKDIR /app

COPY app ./app
COPY routes.json ./routes.json

CMD ["python", "-m", "app.main"]