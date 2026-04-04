import json
import logging
from urllib.parse import quote

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
        """
        Returns a direct URL to the file.
        Note: Since the bucket is configured as PRIVATE, accessing this URL from a browser will return HTTP 403.
        Use generate_presigned_get_url() if you need a link to display in the UI.
        """
        return self._build_raw_url(file_name)

    def generate_presigned_get_url(self, file_name: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for the frontend to view/download the image.
        The bucket is configured as private to avoid unnecessary egress charges.
        """
        if not self.is_ready():
            raise ConnectionError("B2 S3 client is not configured.")
        try:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.B2_BUCKET_NAME, "Key": file_name},
                ExpiresIn=expires_in
            )
        except Exception as e:
            logger.error(f"Failed to generate GET presigned URL: {e}")
            raise

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

    def get_json_file(self, file_name: str) -> list | dict | None:
        if not self.s3_client:
            logger.warning("B2 S3 client not configured, cannot read from B2.")
            return None
        try:
            response = self.s3_client.get_object(Bucket=settings.B2_BUCKET_NAME, Key=file_name)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
                return None
            logger.error(f"Failed to read JSON from B2: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read JSON from B2: {e}")
            return None

    def put_json_file(self, file_name: str, data: list | dict) -> bool:
        if not self.s3_client:
            logger.warning("B2 S3 client not configured, cannot save to B2.")
            return False
        try:
            content = json.dumps(data, ensure_ascii=False)
            self.s3_client.put_object(
                Bucket=settings.B2_BUCKET_NAME,
                Key=file_name,
                Body=content.encode('utf-8'),
                ContentType="application/json"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write JSON to B2: {e}")
            return False