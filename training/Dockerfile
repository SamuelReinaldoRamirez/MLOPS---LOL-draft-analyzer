FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy training scripts
COPY scripts/ ./scripts/

# Models volume will be mounted at /app/models
RUN mkdir -p /app/models

CMD ["python", "scripts/train_all_models.py"]
