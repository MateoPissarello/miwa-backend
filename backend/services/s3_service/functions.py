from __future__ import annotations
import io
from typing import List, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig


class S3Storage:
    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        kms_key_id: Optional[str] = None,
        multipart_threshold_mb: int = 8,  # tune as needed
        max_concurrency: int = 4,
    ):
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

    # -------- Uploads --------
    def upload_fileobj(
        self,
        fileobj,
        key: str,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
        metadata: Optional[dict] = None,
        public: bool = False,
    ) -> str:
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        if cache_control:
            extra["CacheControl"] = cache_control
        if metadata:
            extra["Metadata"] = metadata
        if public:
            extra["ACL"] = "public-read"
        # Encryption (recommended)
        if self.kms_key_id:
            extra.update({"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id})
        else:
            extra.update({"ServerSideEncryption": "AES256"})

        try:
            self.client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=self.bucket,
                Key=key,
                ExtraArgs=extra,
                Config=self.tcfg,
            )
        except ClientError as e:
            raise RuntimeError(f"S3 upload failed for {key}: {e}") from e

        # Prefer presigned URL for private objects
        if public:
            return f"https://{self.bucket}.s3.amazonaws.com/{key}"
        return self.presign_get_url(key)

    # -------- Downloads --------
    def download_to_path(self, key: str, dest_path: str) -> None:
        try:
            self.client.download_file(self.bucket, key, dest_path, Config=self.tcfg)
        except ClientError as e:
            if e.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise FileNotFoundError(key) from e
            raise

    def download_as_bytes(self, key: str) -> bytes:
        try:
            buf = io.BytesIO()
            self.client.download_fileobj(self.bucket, key, buf, Config=self.tcfg)
            buf.seek(0)
            return buf.read()
        except ClientError as e:
            if e.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise FileNotFoundError(key) from e
            raise

    # -------- Listing --------
    def list_keys(self, prefix: str = "", max_items: Optional[int] = None) -> List[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
                if max_items and len(keys) >= max_items:
                    return keys
        return keys

    # -------- Deletes --------
    def delete_key(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True  # S3 delete is idempotent
        except ClientError as e:
            raise RuntimeError(f"Delete failed for {key}: {e}") from e

    def delete_prefix(self, prefix: str) -> int:
        """Bulk delete all keys under a prefix (in batches of 1000). Returns count deleted."""
        to_delete = []
        count = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            while objs:
                batch, objs = objs[:1000], objs[1000:]
                resp = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
                count += len(resp.get("Deleted", []))
        return count

    # -------- Presigned URLs --------
    def presign_get_url(self, key: str, expires_seconds: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def presign_put_url(
        self,
        key: str,
        expires_seconds: int = 900,
        content_type: Optional[str] = None,
    ) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self.client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_seconds,
        )
