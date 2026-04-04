import os
import shutil
import uuid
import logging
from fastapi import UploadFile
from app.core.config import settings
from app.services.b2_service import B2Service

logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class StorageService:
    def __init__(self):
        self.storage_type = (settings.STORAGE_TYPE or "local").lower()
        self.b2_service = B2Service()

    def _should_use_b2(self) -> bool:
        if self.storage_type == "b2":
            return True
        if self.storage_type == "auto":
            return self.b2_service.is_ready()
        return False

    def save_file(self, file: UploadFile) -> str:
        """
        Saves an UploadFile. 
        If B2 is enabled/ready, it uploads to B2 and returns the URL.
        Otherwise, it saves locally and returns the file path.
        """
        file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
        file_name = f"{uuid.uuid4()}.{file_extension}"
        
        # Deterministic behavior: only use B2 when storage type requires it.
        if self._should_use_b2() and self.b2_service.is_ready():
            # Save temporarily to upload to B2
            temp_path = os.path.join(UPLOAD_DIR, file_name)
            try:
                with open(temp_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                # Upload to B2 and get the URL
                file_url = self.b2_service.upload_file(local_file_path=temp_path, file_name=file_name)
                
                # Clean up the temporary local file
                os.remove(temp_path)
                
                return file_url
            except Exception as e:
                logger.error(f"Error during B2 upload, falling back to local storage. Error: {e}")
                # Fallback to local storage if B2 fails
                return self._save_to_local(file, file_name)
        elif self._should_use_b2() and not self.b2_service.is_ready():
            logger.error("STORAGE_TYPE is set to 'b2' but B2 service is not ready. Falling back to local storage.")
            return self._save_to_local(file, file_name)
        else:
            # Default to saving locally
            return self._save_to_local(file, file_name)

    def process_local_file(self, local_path: str) -> str:
        """
        Takes a local file path.
        If B2 is enabled/ready, uploads it to B2, deletes the local file, and returns the B2 URL.
        If local storage is enabled, returns the local path as is.
        """
        # Deterministic behavior for records persistence.
        if self._should_use_b2() and self.b2_service.is_ready():
            file_name = os.path.basename(local_path)
            try:
                file_url = self.b2_service.upload_file(local_file_path=local_path, file_name=file_name)
                # Delete local file after successful upload
                if os.path.exists(local_path):
                    os.remove(local_path)
                return file_url
            except Exception as e:
                logger.error(f"Failed to upload local file {local_path} to B2: {e}")
                # If upload fails, keep the local file and return its path
                return local_path
        elif self._should_use_b2() and not self.b2_service.is_ready():
            logger.error("STORAGE_TYPE is set to 'b2' but B2 service is not ready. Keeping local file.")
            return local_path
        
        return local_path

    def _save_to_local(self, file: UploadFile, file_name: str) -> str:
        file_path = os.path.join(UPLOAD_DIR, file_name)
        try:
            # Reset file pointer if it has been read
            file.file.seek(0)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            return file_path
        except Exception as e:
            logger.error(f"Could not save file locally: {e}")
            raise
