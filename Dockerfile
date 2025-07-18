FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y postgresql-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tmp59q9jhov.xlsx .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "src.bot"]
