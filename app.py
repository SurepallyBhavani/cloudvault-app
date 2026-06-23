import os
import boto3
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION'),endpoint_url=f"https://s3.{os.getenv('AWS_REGION')}.amazonaws.com")
BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    filename = file.filename

    try:
        s3.upload_fileobj(file, BUCKET_NAME, filename)
        return jsonify({"message": f"'{filename}' uploaded successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def get_download_link(filename):
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': filename},
            ExpiresIn=3600  # link valid for 1 hour
        )
        return jsonify({"download_url": url}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)