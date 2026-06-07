FROM python:3.11-slim

# MLflow tracking server. PRODUCTION (Fly) uses a self-contained SQLite backend
# + local artifact store on a mounted volume — no Postgres needed (unlike the
# docker-compose setup, which reuses the postgres service).
RUN pip install --no-cache-dir "mlflow>=2.10.0,<3.0.0"

RUN mkdir -p /mlflow_data/artifacts

EXPOSE 5000

# Bind on IPv6 ([::]) so Fly's proxy (private 6PN) can reach the server. The
# bracketed form is required — MLflow builds "{host}:{port}" for gunicorn, so a
# bare "::" yields an invalid bind ("'' is not a valid port number").
# --workers 1: MLflow's gunicorn defaults to 4 sync workers, which OOMs a small
# machine (each worker loads the full MLflow stack). One worker is plenty here.
CMD ["mlflow", "server", \
     "--host", "[::]", \
     "--port", "5000", \
     "--workers", "1", \
     "--backend-store-uri", "sqlite:////mlflow_data/mlflow.db", \
     "--artifacts-destination", "/mlflow_data/artifacts", \
     "--serve-artifacts"]
