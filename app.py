import os
import logging
import boto3
import psycopg2
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from dotenv import load_dotenv

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

s3 = boto3.client('s3', region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'), sslmode='require'
    )

@app.route('/upload', methods=['POST'])
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
            "INSERT INTO file_uploads (filename, s3_key, upload_time, expiry_time) VALUES (%s, %s, %s, %s)",
            (filename, filename, upload_time, expiry_time)
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Metadata logged to RDS for: {filename}")

        return jsonify({"message": f"'{filename}' uploaded successfully"}), 200
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def get_download_link(filename):
    try:
        url = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET_NAME, 'Key': filename}, ExpiresIn=3600)
        logger.info(f"Presigned URL generated for: {filename}")
        return jsonify({"download_url": url}), 200
    except Exception as e:
        logger.error(f"Download link generation failed for {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)