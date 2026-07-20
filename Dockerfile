FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    postgresql-client \
    build-essential \
    python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip uninstall -y greenlet || true \
 && pip install --no-cache-dir --no-binary=:all: greenlet \
 && pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "src.bot"]
