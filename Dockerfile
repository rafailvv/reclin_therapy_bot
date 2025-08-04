FROM python:3.11-slim

# Добавляем репозиторий PostgreSQL 16
RUN apt-get update \
 && apt-get install -y wget gnupg2 lsb-release \
 && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
 && echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y postgresql-client-16 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# COPY tmp59q9jhov.xlsx .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "src.bot"]
