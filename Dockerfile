FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY gear_miner /app/gear_miner

RUN pip install --no-cache-dir .

RUN mkdir -p /app/data/ui && useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE 8765

CMD ["python", "-m", "gear_miner", "ui", "--host", "0.0.0.0", "--port", "8765", "--data-dir", "/app/data/ui"]
