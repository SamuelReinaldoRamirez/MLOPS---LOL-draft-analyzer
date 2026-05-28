FROM python:3.11-slim

WORKDIR /mlflow

# System deps: psql client (entrypoint creates the mlflow DB if missing) + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps (mlflow server + postgres driver)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Artifacts are stored on a mounted volume at /mlflow/artifacts
RUN mkdir -p /mlflow/artifacts

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
