import os
import logging
from functools import wraps
import boto3
import psycopg2
import psycopg2.errors
import jwt
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('cloudvault.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

REGION = os.getenv('AWS_REGION').strip()
BUCKET_NAME = os.getenv('S3_BUCKET_NAME').strip()
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = 8

s3 = boto3.client('s3', region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'), sslmode='require'
    )
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "missing or malformed Authorization header"}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            # 'algorithms' is a fixed allow-list, not read from the token itself --
            # this is what stops an "alg confusion" / "alg: none" JWT attack, where a
            # forged token claims a different (or no) algorithm to bypass verification.
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401

        request.user_id = payload['user_id']
        request.username = payload['username']
        return f(*args, **kwargs)
    return decorated

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    password_hash = generate_password_hash(password)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, password_hash)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        logger.info(f"New user registered: {username}")
        return jsonify({"message": "user registered", "user_id": user_id}), 201
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({"error": "username already taken"}), 409
    except Exception as e:
        logger.error(f"Registration failed for {username}: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    # Deliberately the SAME error for "no such user" and "wrong password" --
    # telling an attacker which one was wrong lets them enumerate valid usernames.
    if row is None or not check_password_hash(row[1], password):
        logger.warning(f"Failed login attempt for username: {username}")
        return jsonify({"error": "invalid username or password"}), 401

    user_id = row[0]
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.info(f"User logged in: {username}")
    return jsonify({"token": token}), 200

@app.route('/upload', methods=['POST'])
@require_auth
def upload_file():
    if 'file' not in request.files:
        logger.warning("Upload attempt with no file provided")
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    filename = file.filename
    try:
        s3.upload_fileobj(file, BUCKET_NAME, filename)
        logger.info(f"File uploaded to S3: {filename}")

        upload_time = datetime.now(timezone.utc)
        expiry_time = upload_time + timedelta(hours=24)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO file_uploads (filename, s3_key, upload_time, expiry_time, owner_id) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (filename, filename, upload_time, expiry_time, request.user_id)
        )
        file_id = cur.fetchone()[0]

        # The uploader automatically gets permission to download their own file --
        # this is the row that makes them the "owner" in practice, not just in name.
        cur.execute(
            "INSERT INTO file_permissions (file_id, user_id) VALUES (%s, %s)",
            (file_id, request.user_id)
        )

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Metadata logged to RDS for: {filename} (owner: {request.username})")

        return jsonify({"message": f"'{filename}' uploaded successfully"}), 200
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/files/<filename>/share', methods=['POST'])
@require_auth
def share_file(filename):
    data = request.get_json(silent=True) or {}
    target_username = data.get('username', '').strip()

    if not target_username:
        return jsonify({"error": "username is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, owner_id FROM file_uploads WHERE filename = %s", (filename,))
    file_row = cur.fetchone()
    if file_row is None:
        cur.close()
        conn.close()
        return jsonify({"error": "file not found"}), 404

    file_id, owner_id = file_row

    # Only the owner can grant access -- otherwise someone merely SHARED a file
    # could re-share it further without the owner ever agreeing to that.
    if owner_id != request.user_id:
        cur.close()
        conn.close()
        logger.warning(f"User {request.username} tried to share '{filename}' without owning it")
        return jsonify({"error": "only the file owner can share it"}), 403

    cur.execute("SELECT id FROM users WHERE username = %s", (target_username,))
    target_row = cur.fetchone()
    if target_row is None:
        cur.close()
        conn.close()
        return jsonify({"error": f"user '{target_username}' does not exist"}), 404

    target_user_id = target_row[0]

    try:
        cur.execute(
            "INSERT INTO file_permissions (file_id, user_id) VALUES (%s, %s)",
            (file_id, target_user_id)
        )
        conn.commit()
        message = f"'{filename}' shared with {target_username}"
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        message = f"{target_username} already has access to '{filename}'"
    finally:
        cur.close()
        conn.close()

    logger.info(message)
    return jsonify({"message": message}), 200

@app.route('/download/<filename>', methods=['GET'])
@require_auth
def get_download_link(filename):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM file_uploads WHERE filename = %s", (filename,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            conn.close()
            return jsonify({"error": "file not found"}), 404

        file_id = row[0]
        cur.execute(
            "SELECT 1 FROM file_permissions WHERE file_id = %s AND user_id = %s",
            (file_id, request.user_id)
        )
        has_permission = cur.fetchone() is not None
        cur.close()
        conn.close()

        if not has_permission:
            logger.warning(f"User {request.username} denied access to {filename} (no permission granted)")
            return jsonify({"error": "you do not have permission to download this file"}), 403

        url = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET_NAME, 'Key': filename}, ExpiresIn=3600)
        logger.info(f"Presigned URL generated for: {filename} (requested by {request.username})")
        return jsonify({"download_url": url}), 200
    except Exception as e:
        logger.error(f"Download link generation failed for {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)