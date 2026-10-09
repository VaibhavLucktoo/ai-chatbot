FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.18
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini run.py ./
RUN useradd --create-home chatbot && mkdir -p /app/.cache && chown chatbot:chatbot /app/.cache
USER chatbot
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
# Host networking preserves loopback checks; this container runs on Linux.
CMD ["python", "run.py"]
