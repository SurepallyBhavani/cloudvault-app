import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)
print(f"DB_HOST={os.getenv('DB_HOST')}")
print(f"DB_USER={os.getenv('DB_USER')}")
print(f"DB_PASSWORD={os.getenv('DB_PASSWORD')}")

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    sslmode='require'
)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS file_uploads (
        id SERIAL PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        s3_key VARCHAR(512) NOT NULL,
        upload_time TIMESTAMPTZ DEFAULT NOW(),
        expiry_time TIMESTAMPTZ
    );
""")
conn.commit()
print("Table 'file_uploads' created successfully.")

cur.close()
conn.close()