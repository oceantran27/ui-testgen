"""
DEPRECATED: This module is no longer needed.

Import StorageService directly from storage_service.py instead:
    from app.services.storage_service import StorageService

This compatibility wrapper is kept for backward compatibility only and may be removed in a future version.
"""

from app.services.storage_service import StorageService

__all__ = ["StorageService"]


