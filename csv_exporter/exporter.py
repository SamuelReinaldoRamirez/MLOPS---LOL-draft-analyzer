#importe juste la table matches
import pandas as pd
import psycopg2
import os

print("🚀 Starting CSV export...")

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
    port=5432
)

print("✅ Connected to DB")

query = "SELECT * FROM matches"

df = pd.read_sql(query, conn)

print(f"📊 Number of rows fetched: {len(df)}")

output_path = "/data/matches.csv"
df.to_csv(output_path, index=False)

print(f"✅ CSV written to {output_path}")



# importe toutes les tables en csv
# import pandas as pd
# import psycopg2
# import os

# print("🚀 Starting FULL CSV export...")

# conn = psycopg2.connect(
#     dbname=os.getenv("POSTGRES_DB"),
#     user=os.getenv("POSTGRES_USER"),
#     password=os.getenv("POSTGRES_PASSWORD"),
#     host=os.getenv("POSTGRES_HOST"),
#     port=5432
# )

# print("✅ Connected to DB")

# cur = conn.cursor()

# # récupère toutes les tables public
# cur.execute("""
#     SELECT tablename
#     FROM pg_tables
#     WHERE schemaname = 'public'
# """)

# tables = [t[0] for t in cur.fetchall()]

# print(f"📦 Found tables: {tables}")

# os.makedirs("/data", exist_ok=True)

# for table in tables:
#     print(f"➡ Exporting {table}...")

#     df = pd.read_sql(f"SELECT * FROM {table}", conn)

#     output_path = f"/data/{table}.csv"
#     df.to_csv(output_path, index=False)

#     print(f"✅ {table} -> {len(df)} rows saved")

# cur.close()
# conn.close()

# print("🎉 Export completed")