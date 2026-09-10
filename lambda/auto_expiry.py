import os
import boto3
from datetime import datetime, timezone, timedelta

REGION = os.environ.get('AWS_REGION', 'ap-south-1')

s3 = boto3.client(
    's3',
    region_name=REGION,
    endpoint_url=f'https://s3.{REGION}.amazonaws.com'
)
BUCKET_NAME = os.environ['S3_BUCKET_NAME']  # set in the Lambda's environment variables
EXPIRY_HOURS = 24

def lambda_handler(event, context):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=EXPIRY_HOURS)
    response = s3.list_objects_v2(Bucket=BUCKET_NAME)

    if 'Contents' not in response:
        print("Bucket is empty, nothing to check.")
        return {"deleted": []}

    deleted = []
    for obj in response['Contents']:
        if obj['LastModified'] < cutoff:
            s3.delete_object(Bucket=BUCKET_NAME, Key=obj['Key'])
            deleted.append(obj['Key'])
            print(f"Deleted expired file: {obj['Key']}")

    print(f"Total deleted: {len(deleted)}")
    return {"deleted": deleted}