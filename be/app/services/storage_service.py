import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import UploadFile
from typing import Optional, List
import io
import os
from app.core.config import settings
from app.core.logging import logger

class StorageService:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1', # Dummy region for minio
            use_ssl=settings.STORAGE_SECURE
        )
        self.bucket_name = settings.STORAGE_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.info(f"Bucket {self.bucket_name} does not exist, creating it.")
                try:
                    self.s3.create_bucket(Bucket=self.bucket_name)
                except Exception as ex:
                    logger.error(f"Failed to create bucket: {ex}")
            else:
                logger.error(f"Error checking bucket {self.bucket_name}: {e}")

    def upload_file(self, file_content: bytes, object_name: str, content_type: str = 'application/octet-stream') -> str:
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=object_name,
                Body=file_content,
                ContentType=content_type
            )
            # Return relative URI style
            return f"s3://{self.bucket_name}/{object_name}"
        except ClientError as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            raise

    def get_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        try:
            response = self.s3.generate_presigned_url('get_object',
                                                    Params={'Bucket': self.bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
            return response
        except ClientError as e:
            logger.error(f"Failed to generate presigned url for {object_name}: {e}")
            return None

    def object_exists(self, object_name: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError:
            return False

    def download_file(self, object_name: str) -> bytes:
        """Download an object from storage and return its bytes."""
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=object_name)
            return response['Body'].read()
        except ClientError as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            raise

    @staticmethod
    def s3_uri_to_bucket_and_key(storage_uri: str) -> tuple[Optional[str], str]:
        """
        Parse s3://bucket/key into (bucket, key). If not an s3:// URI, returns (None, storage_uri).
        """
        if not storage_uri.startswith("s3://"):
            return None, storage_uri
        rest = storage_uri[5:]
        parts = rest.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, rest

    def download_from_uri(self, storage_uri: str) -> bytes:
        """Download using either an s3://bucket/key URI or a bare object key."""
        bucket, key = self.s3_uri_to_bucket_and_key(storage_uri)
        if bucket and bucket != self.bucket_name:
            logger.warning(
                f"S3 URI bucket '{bucket}' != configured bucket '{self.bucket_name}'; "
                "fetching key against configured bucket"
            )
        return self.download_file(key)

    def list_objects(self, prefix: str) -> List[str]:
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            return []
        except ClientError as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            return []

storage_service = StorageService()
