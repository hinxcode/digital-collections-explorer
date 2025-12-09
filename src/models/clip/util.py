import boto3
from typing import Any
import os


def create_client():
    client = boto3.session.Session().client("s3")
    return client

def get_file_names(
        client: Any, 
        bucket: str,
        prefix: str):
    
    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/')
    filenames = []
    for page in pages:
        for obj in page['Contents']:
            if not obj["Key"].endswith("/"):
                filenames.append(obj["Key"])
    return filenames


def download_file(client: Any, bucket: str, filename: str, destination: str):
    # Get the directory path (everything except the filename)
    directory = os.path.dirname(destination)

    # Create the directory structure if it doesn't exist
    # exist_ok=True means no error if directory already exists
    if directory:  # Only create if there's actually a directory path
        os.makedirs(directory, exist_ok=True)

    client.download_file(bucket, filename, destination)
