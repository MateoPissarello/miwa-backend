"""Lightweight S3 helper mirroring the backend storage behaviour."""

from __future__ import annotations

import io
from typing import Optional

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError


class S3Storage:
    def __init__(
        self,
        *,
        bucket: str,
        region: Optional[str] = None,
        kms_key_id: Optional[str] = None,
        multipart_threshold_mb: int = 8,
        max_concurrency: int = 4,
    ) -> None:
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self.client = boto3.client(
            "s3",
            region_name=region,
            config=Config(
                retries={"max_attempts": 10, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )
        self.tcfg = TransferConfig(
            multipart_threshold=multipart_threshold_mb * 1024 * 1024,
            max_concurrency=max_concurrency,
            multipart_chunksize=8 * 1024 * 1024,
            use_threads=True,
        )

    def upload_bytes(
        self,
        *,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        return self.upload_fileobj(
            fileobj=io.BytesIO(data),
            key=key,
            content_type=content_type,
            cache_control=cache_control,
            metadata=metadata,
        )

    def upload_fileobj(
        self,
        *,
        fileobj,
        key: str,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        if cache_control:
            extra["CacheControl"] = cache_control
        if metadata:
            extra["Metadata"] = metadata
        if self.kms_key_id:
            extra.update({"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id})
        else:
            extra.update({"ServerSideEncryption": "AES256"})

        try:
            fileobj.seek(0)
            self.client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=self.bucket,
                Key=key,
                ExtraArgs=extra,
                Config=self.tcfg,
            )
        except ClientError as exc:
            raise RuntimeError(f"Failed to upload {key}: {exc}") from exc
        return self.presign_get_url(key)

    def download_text(self, *, key: str, encoding: str = "utf-8") -> str:
        try:
            buf = io.BytesIO()
            self.client.download_fileobj(self.bucket, key, buf, Config=self.tcfg)
        except ClientError as exc:
            raise RuntimeError(f"Failed to download {key}: {exc}") from exc
        buf.seek(0)
        return buf.read().decode(encoding)

    def presign_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

