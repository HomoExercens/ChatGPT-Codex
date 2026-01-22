FROM postgres:16-alpine

RUN apk add --no-cache bash ca-certificates python3 py3-pip && \
    pip3 install --no-cache-dir boto3

WORKDIR /app
COPY scripts /app/scripts
RUN chmod +x /app/scripts/backup_pg_to_s3.sh /app/scripts/restore_pg_from_s3.sh

ENV PYTHONUNBUFFERED=1

CMD ["bash", "-lc", "while true; do /app/scripts/backup_pg_to_s3.sh || true; sleep ${NEUROLEAGUE_BACKUP_INTERVAL_SEC:-86400}; done"]

