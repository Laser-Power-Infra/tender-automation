import boto3
from pathlib import Path
from django.conf import settings


def _client():
    # ponytail: global client, per-call client if credential rotation needed
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY or None,
        aws_secret_access_key=settings.S3_SECRET_KEY or None,
        region_name=getattr(settings, "S3_REGION", "us-east-1"),
    )


class FileStorageService:
    # ponytail: single self-hosted bucket, per-referenceNo prefix, no mkdir needed (S3 prefix)
    def upload(self, file_path, reference_no=None, key=None, extra_args=None):
        p = Path(file_path)
        fname = key or p.name
        k = f"{reference_no.strip('/')}/{fname}" if reference_no else fname
        bucket = settings.S3_BUCKET
        _client().upload_file(str(p), bucket, k, ExtraArgs=extra_args or {})
        url = f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{bucket}/{k}"
        return {"bucket": bucket, "key": k, "url": url}

    # ponytail: no presigned URL, add generate_presigned_url when frontend needs it


file_storage = FileStorageService()
