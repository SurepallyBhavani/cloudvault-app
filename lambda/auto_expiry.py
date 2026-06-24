import boto3
from datetime import datetime, timezone, timedelta

s3 = boto3.client(
    's3',
    region_name='ap-south-1',
    endpoint_url='https://s3.ap-south-1.amazonaws.com'
)
BUCKET_NAME = 'cloudvault-files-<your-full-bucket-name>'  # use your full Account Regional Namespace name
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