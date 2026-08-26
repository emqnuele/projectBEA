# ProjectBEA — one image that carries the engine, the dashboard and the Discord bot.
#
#   docker compose run --rm setup   # answer five questions
#   docker compose up               # http://127.0.0.1:8000
#
# What works in a container: the dashboard, memory, Discord (voice included, it
# travels over the network), Telegram, Twitch, Minecraft.
# What does not: her speaking out of the host's speakers. That needs a real audio
# device — on Linux, uncomment the `devices:` block in compose; on macOS and
# Windows, Docker Desktop cannot pass one through, so run natively for streaming.

# --- 1. the dashboard -------------------------------------------------------

FROM node:20-bookworm-slim AS dashboard

WORKDIR /build
COPY src/web/frontend/package.json src/web/frontend/package-lock.json ./
RUN npm ci
COPY src/web/frontend/ ./
RUN npm run build

# --- 2. the discord bot's dependencies --------------------------------------
# built on the runtime's own base image so the native modules (@discordjs/opus,
# libsodium) match the node ABI they will actually run against

FROM python:3.12-slim-bookworm AS botdeps

RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs npm build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /bot
COPY src/core/skills/voice/bot/package.json src/core/skills/voice/bot/package-lock.json ./
RUN npm ci --omit=dev

# --- 3. the runtime ---------------------------------------------------------

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TOKENIZERS_PARALLELISM=false

# libportaudio2: sounddevice fails to import without it, device or no device
# libsndfile1:   decodes the mp3 EdgeTTS produces
# ffmpeg:        @discordjs/voice transcodes through it
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs \
        libportaudio2 \
        libsndfile1 \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv

WORKDIR /app

# dependencies resolve in their own layer, so editing source does not re-install
# 167 packages
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src/ ./src/
COPY main.py config.example.json ./
COPY data/prompts/ ./data/prompts/

COPY --from=dashboard /build/dist ./src/web/frontend/dist
COPY --from=botdeps /bot/node_modules ./src/core/skills/voice/bot/node_modules

RUN uv sync --locked --no-dev

# everything she remembers, plus the config the wizard writes
VOLUME ["/app/data"]

EXPOSE 8000

# 0.0.0.0 binds inside the container only. The API has no authentication, so
# compose publishes the port to 127.0.0.1 and never to the host's real address.
ENTRYPOINT ["uv", "run", "bea"]
CMD ["--web", "--host", "0.0.0.0"]
