FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/requirements.txt

COPY services /app/services
COPY packages /app/packages
COPY scripts /app/scripts

ENV PYTHONPATH=/app/services/api:/app/packages/sim:/app/packages/rl:/app/packages/shared
ENV NEUROLEAGUE_DB_URL=sqlite:////app/artifacts/neuroleague.db
ENV NEUROLEAGUE_ARTIFACTS_DIR=/app/artifacts

EXPOSE 8000

CMD ["bash", "-lc", "mkdir -p /app/artifacts && alembic -c /app/services/api/alembic.ini upgrade head && python /app/scripts/seed_data.py && uvicorn neuroleague_api.main:app --host 0.0.0.0 --port 8000"]
