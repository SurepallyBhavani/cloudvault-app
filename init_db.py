import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)
print(f"Connecting to DB_HOST={os.getenv('DB_HOST')} (username/password not printed)")

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

# --- Auth + access control schema ---

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(80) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
""")
conn.commit()
print("Table 'users' created successfully.")

cur.execute("""
    ALTER TABLE file_uploads ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id);
""")
conn.commit()
print("Column 'owner_id' added to file_uploads.")

cur.execute("""
    CREATE TABLE IF NOT EXISTS file_permissions (
        id SERIAL PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(file_id, user_id)
    );
""")
conn.commit()
print("Table 'file_permissions' created successfully.")

cur.close()
conn.close()