# Multi-agent LangChain: one image runs orchestrator or any agent via CMD.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY migrations ./migrations
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .

# Default: run orchestrator (override in docker-compose per service)
ENV PORT=8000
EXPOSE 8000 8001 8002 8003

CMD ["python", "-m", "src.orchestrator.main"]
