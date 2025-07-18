#!/usr/bin/env sh
set -e

echo "⏳ Waiting for Postgres at $POSTGRES_HOST:$POSTGRES_PORT…"
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
  sleep 1
done

echo "🚀 Applying alembic migrations…"
alembic upgrade head

# hand off to whatever CMD you set in the Dockerfile
exec "$@"
