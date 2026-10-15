# Build from the repository root: docker build -t ai-chatbot .
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run lint && npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.18
COPY Backend/pyproject.toml Backend/uv.lock ./
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY Backend/app ./app
COPY Backend/scripts ./scripts
COPY Backend/migrations ./migrations
COPY Backend/alembic.ini Backend/run.py ./
COPY --from=frontend /build/dist ./frontend_dist
# Bake the pinned embedding assets into the image; startup never needs a fresh download.
RUN python -m scripts.cache_embeddings
RUN useradd --create-home chatbot && chown -R chatbot:chatbot /app/.cache
USER chatbot
EXPOSE 8000
# One process: admin tokens, request limits and recovery are process-local.
CMD ["sh", "-c", "alembic upgrade head && exec python run.py"]
