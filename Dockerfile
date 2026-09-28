# Container image for the sweep (run it from a scheduler) and the console.
#   docker build -t legal-intake .
#   docker run --rm --env-file .env -v $(pwd)/data:/app/data legal-intake intake sweep
#   docker run --rm --env-file .env -v $(pwd)/data:/app/data -p 8000:8000 legal-intake intake serve
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

COPY areas ./areas
COPY fixtures ./fixtures
ENV PATH="/app/.venv/bin:$PATH" STATE_DB=/app/data/state.sqlite
VOLUME ["/app/data"]

CMD ["intake", "sweep"]
