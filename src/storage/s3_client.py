import asyncio
from dataclasses import dataclass

import boto3
from botocore.config import Config


@dataclass
class StoredObject:
    body: bytes
    content_length: int


class S3Storage:
    """Raw Document bytes live in MinIO through the S3 API (NBK-5). boto3 is synchronous, so
    every call runs in a thread; `path` addressing because MinIO has no virtual-host style.
    Both the SDK and MinIO itself reset connections now and then, hence the generous retries."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ):
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )

    async def ensure_bucket(self) -> None:
        """Creates the bucket if it doesn't already exist. Idempotent."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
        except Exception:  # noqa: BLE001
            await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)

    async def put_object(self, key: str, body: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    async def get_object(self, key: str) -> StoredObject:
        def read() -> StoredObject:
            result = self._client.get_object(Bucket=self.bucket, Key=key)
            return StoredObject(
                body=result["Body"].read(), content_length=result["ContentLength"]
            )

        return await asyncio.to_thread(read)
