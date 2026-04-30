from fastapi import FastAPI
import random
from app.db import get_conn

app = FastAPI()


@app.get("/predict")
def predict():
    return {"prediction": f"{random.random()}"}


@app.get("/table")
def table_count():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM matches;")
    count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {"matches_count": count}