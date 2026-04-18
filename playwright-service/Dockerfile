FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    && pip install --no-cache-dir playwright fastapi uvicorn httpx \
    && playwright install chromium \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3002"]
