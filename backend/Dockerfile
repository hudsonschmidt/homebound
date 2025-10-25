# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/venv/bin:$PATH"

WORKDIR /app

# System deps (if you add c-ext later, add build tools here)
RUN python -m venv /venv

# Copy project metadata first for caching
COPY backend/pyproject.toml backend/README.md /app/
RUN pip install --upgrade pip && pip install -e ".[dev]"  # remove [dev] for prod if you want

# Copy app code
COPY backend/app /app/app

# Default port hint (some hosts read $PORT)
ENV PORT=8080

# Run uvicorn (1 worker is fine for staging; scale at the platform)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
