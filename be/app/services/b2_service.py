import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, unquote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ConnectTimeoutError, ReadTimeoutError

from app.core.config import settings

logger = logging.getLogger(__name__)

class B2Service:
    def __init__(self):
        self.s3_client = None
        
        try:
            key_id = settings.B2_KEY_ID
            app_key = settings.B2_APPLICATION_KEY
            endpoint = self._normalize_endpoint(settings.B2_ENDPOINT)
            
            if key_id and app_key and settings.B2_REGION and endpoint:
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    aws_access_key_id=key_id,
                    aws_secret_access_key=app_key,
                    region_name=settings.B2_REGION,
                    config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10),
                )
                logger.info("B2 S3 service initialized successfully.")
            else:
                logger.warning("B2 S3 credentials or settings are not fully configured.")
        except Exception as e:
            logger.error(f"Failed to initialize B2 S3 service: {e}")

    def is_ready(self) -> bool:
        return self.s3_client is not None

    @staticmethod
    def _normalize_endpoint(endpoint: str | None) -> str | None:
        if not endpoint:
            return None
        cleaned = endpoint.strip().rstrip("/")
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        return cleaned

    def _build_raw_url(self, file_name: str) -> str:
        """Build raw URL according to Object Storage architecture."""
        endpoint = self._normalize_endpoint(settings.B2_ENDPOINT)
        if endpoint:
            encoded_name = quote(file_name)
            return f"{endpoint}/{settings.B2_BUCKET_NAME}/{encoded_name}"
        raise ConnectionError("Could not build B2 download URL.")

    def get_file_url(self, file_name: str) -> str:
        """Return the raw object URL for a key."""
        return self._build_raw_url(file_name)

    @staticmethod
    def extract_key_from_url(file_url: str) -> str | None:
        if not file_url:
            return None
        try:
            parsed = urlparse(file_url)
            path = parsed.path.strip("/")
            if not path:
                return None

            bucket_name = (settings.B2_BUCKET_NAME or "").strip("/")
            candidates = [path]

            if bucket_name and path.startswith(f"{bucket_name}/"):
                candidates.insert(0, path[len(bucket_name) + 1 :])

            # Some URL shapes include vendor prefixes before bucket/key.
            if bucket_name and f"/{bucket_name}/" in f"/{path}":
                suffix = path.split(f"{bucket_name}/", 1)[-1]
                if suffix:
                    candidates.insert(0, suffix)

            for candidate in candidates:
                normalized = unquote(candidate).strip("/")
                if normalized:
                    return normalized

            return None
        except Exception:
            return None

    def upload_file(self, local_file_path: str, file_name: str, content_type: str = None) -> str:
        """Upload a file to B2 using boto3 S3 standard."""
        if not self.is_ready():
            raise ConnectionError("B2 service is not ready.")
        
        try:
            logger.info(f"Uploading {file_name} to B2 via boto3...")
            # boto3 upload_file handles multipart uploads automatically for large files
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
                
            self.s3_client.upload_file(
                Filename=local_file_path,
                Bucket=settings.B2_BUCKET_NAME,
                Key=file_name,
                ExtraArgs=extra_args if extra_args else None
            )
            
            download_url = self._build_raw_url(file_name)
            logger.info(f"File {file_name} uploaded to B2. Raw URL: {download_url}")
            return download_url
        except Exception as e:
            logger.error(f"Failed to upload file to B2 via boto3: {e}")
            raise

    def generate_presigned_put_url(self, file_name: str, content_type: str = None) -> str:
        """
        Generate a presigned PUT URL for direct file uploads.
        ContentType must be included to pass CORS preflight checks.
        """
        if not file_name:
            raise ValueError("file_name is required")
        if not self.s3_client:
            raise ConnectionError("B2 S3 client is not configured.")

        try:
            params = {
                "Bucket": settings.B2_BUCKET_NAME, 
                "Key": file_name
            }
            # Include ContentType in the signature to pass CORS checks
            if content_type:
                params["ContentType"] = content_type

            return self.s3_client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=settings.B2_PRESIGNED_EXPIRES_SECONDS,
                HttpMethod="PUT",
            )
        except (ConnectTimeoutError, ReadTimeoutError, BotoCoreError, ClientError) as e:
            logger.error(f"Failed to generate B2 presigned PUT URL: {e}")
            raise TimeoutError("Timed out while generating B2 presigned URL") from e

    def generate_presigned_get_url(self, file_name: str) -> str:
        """Generate a presigned GET URL for private object downloads."""
        if not file_name:
            raise ValueError("file_name is required")
        if not self.s3_client:
            raise ConnectionError("B2 S3 client is not configured.")

        try:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.B2_BUCKET_NAME, "Key": file_name},
                ExpiresIn=settings.B2_PRESIGNED_GET_EXPIRES_SECONDS,
                HttpMethod="GET",
            )
        except (ConnectTimeoutError, ReadTimeoutError, BotoCoreError, ClientError) as e:
            logger.error(f"Failed to generate B2 presigned GET URL: {e}")
            raise TimeoutError("Timed out while generating B2 presigned download URL") from e

    def list_keys(self, prefix: str, older_than: datetime | None = None) -> list[str]:
        if not self.is_ready():
            return []

        keys: list[str] = []
        token: str | None = None
        safe_prefix = (prefix or "").strip().strip("/")
        if safe_prefix:
            safe_prefix = f"{safe_prefix}/"

        while True:
            params: dict[str, Any] = {
                "Bucket": settings.B2_BUCKET_NAME,
                "Prefix": safe_prefix,
                "MaxKeys": 1000,
            }
            if token:
                params["ContinuationToken"] = token

            response = self.s3_client.list_objects_v2(**params)
            for obj in response.get("Contents", []):
                key = obj.get("Key")
                if not key:
                    continue

                if older_than is not None:
                    last_modified = obj.get("LastModified")
                    if not isinstance(last_modified, datetime):
                        continue
                    cutoff = older_than
                    if cutoff.tzinfo is None:
                        cutoff = cutoff.replace(tzinfo=timezone.utc)
                    if last_modified >= cutoff:
                        continue

                keys.append(key)

            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
            if not token:
                break

        return keys

    def delete_file(self, key: str) -> bool:
        if not self.is_ready() or not key:
            return False
        try:
            self.s3_client.delete_object(Bucket=settings.B2_BUCKET_NAME, Key=key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete file from B2 ({key}): {e}")
            return False

    def delete_files(self, keys: list[str]) -> int:
        if not self.is_ready() or not keys:
            return 0

        deleted = 0
        chunk_size = 1000
        for i in range(0, len(keys), chunk_size):
            chunk = [k for k in keys[i:i + chunk_size] if k]
            if not chunk:
                continue
            try:
                response = self.s3_client.delete_objects(
                    Bucket=settings.B2_BUCKET_NAME,
                    Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
                )
                deleted += len(response.get("Deleted", []))
            except Exception as e:
                logger.error(f"Failed to batch delete files from B2: {e}")
        return deleted

