# Multi-page Streamlit app — build context is the REPO ROOT (needs streamlit_app/
# + src/). Reads match data from the MLOPS Postgres; models come from the shared
# `models` compose volume mounted at /app/models (populated by `make seed`).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY streamlit_app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app/ ./streamlit_app/
COPY src/ ./src/
COPY streamlit/.streamlit/ ./.streamlit/

ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "streamlit_app/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
