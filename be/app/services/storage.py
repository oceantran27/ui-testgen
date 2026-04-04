"""Compatibility module for storage service imports.

Use this module when callers import `app.services.storage`.
"""

from app.services.storage_service import StorageService


def get_storage_service() -> StorageService:
	return StorageService()

