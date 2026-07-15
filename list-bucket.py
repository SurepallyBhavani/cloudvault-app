import boto3

# boto3 automatically picks up credentials from `aws configure`
# (stored in ~/.aws/credentials) — no keys hardcoded here
s3 = boto3.client('s3', region_name='ap-south-1')

BUCKET_NAME = 'cloudvault-files-562904761107-ap-south-1-an'

def list_bucket_contents():
    response = s3.list_objects_v2(Bucket=BUCKET_NAME)
    
    if 'Contents' not in response:
        print(f"Bucket '{BUCKET_NAME}' is empty.")
        return
    
    print(f"Contents of '{BUCKET_NAME}':")
    for obj in response['Contents']:
        print(f" - {obj['Key']} ({obj['Size']} bytes, last modified {obj['LastModified']})")

if __name__ == "__main__":
    list_bucket_contents()