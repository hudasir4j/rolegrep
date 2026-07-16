# Build frontend
FROM node:20-alpine AS frontend
WORKDIR /web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# Runtime
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROLEGREP_DATA_DIR=/app/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY eval ./eval
COPY --from=frontend /web/dist ./web/dist

RUN pip install --no-cache-dir -e ".[agent,api]"

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "rolegrep.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
