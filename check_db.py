import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    sslmode='require'
)

cur = conn.cursor()
cur.execute("SELECT * FROM file_uploads;")
rows = cur.fetchall()

if not rows:
    print("No rows found in file_uploads table.")
else:
    print(f"{len(rows)} row(s) found:\n")
    for row in rows:
        print(f"id={row[0]}, filename={row[1]}, s3_key={row[2]}, upload_time={row[3]}, expiry_time={row[4]}")

cur.close()
conn.close()