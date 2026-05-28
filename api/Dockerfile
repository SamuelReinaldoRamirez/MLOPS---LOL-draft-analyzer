FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps (resilient to slow/flaky PyPI on large ML wheels)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 180 --retries 10 -r requirements.txt

# Copy application code
COPY app/ ./app/

# Bake any staged model_*.pkl into the image so PaaS deploys (no docker volume)
# find models at /app/models (default MODELS_DIR). The build context is ./api,
# so this copies api/models/ — which always exists (.gitkeep) and may contain
# model_*.pkl staged via scripts/stage_models_for_image.sh before the build.
# Locally, the docker-compose `models` volume shadows this path, so the seeded
# volume still wins and local behavior is unchanged.
COPY models/ /app/models/

EXPOSE 8000

HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
