import boto3
from typing import Any

def create_client():
    client = boto3.session.Session(profile_name="default").client('s3')
    return client

def get_file_names(
        client: Any, 
        bucket: str,
        prefix: str):
    return client.list_objects(Bucket=bucket, Prefix=prefix)


