FROM python:3.15-slim AS build

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install poetry poetry-plugin-export

COPY pyproject.toml poetry.lock /app/
# Export the locked runtime set and install it into a self-contained prefix.
# --ignore-installed: Poetry itself already pulled some of these into this stage, and pip would
# otherwise skip them — leaving them out of /install and out of the final image.
RUN poetry export --without dev --format requirements.txt --output requirements.txt \
    && pip install --ignore-installed --prefix=/install -r requirements.txt


FROM python:3.15-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    TZ=Europe/Kyiv \
    HEARTBEAT_FILE=/tmp/ya32.heartbeat

WORKDIR /app
COPY --from=build /install /usr/local
COPY alembic.ini /app/
COPY migrations /app/migrations
COPY src /app/src

# Non-root: the bot needs no privileges, it only talks to Telegram and Postgres.
RUN useradd --create-home --uid 10001 bot && mkdir -p /app/data && chown bot /app/data
USER bot

# Alive = the scheduler touched the heartbeat within the last 3 minutes.
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime(os.environ['HEARTBEAT_FILE'])<180 else 1)"

CMD ["python", "-m", "ya32_bot"]
