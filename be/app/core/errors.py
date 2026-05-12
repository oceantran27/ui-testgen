from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
import uuid


class BaseAPIException(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        self.request_id = str(uuid.uuid4())
        super().__init__(self.message)


# ──────────────────────────────────────────────
# Generic exceptions (Phase 0)
# ──────────────────────────────────────────────

class ResourceNotFoundException(BaseAPIException):
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            error_code="RESOURCE_NOT_FOUND",
            message=f"{resource_type} with id '{resource_id}' not found.",
            status_code=404
        )


class InvalidRequestException(BaseAPIException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="INVALID_REQUEST",
            message=message,
            details=details,
            status_code=400
        )


# ──────────────────────────────────────────────
# Phase 1 – Run-specific exceptions
# ──────────────────────────────────────────────

class RunNotFoundException(BaseAPIException):
    def __init__(self, run_id: str):
        super().__init__(
            error_code="RUN_NOT_FOUND",
            message=f"Run '{run_id}' not found.",
            status_code=404
        )


class RunNotUploadableException(BaseAPIException):
    def __init__(self, run_id: str, current_status: str):
        super().__init__(
            error_code="RUN_NOT_UPLOADABLE",
            message=f"Run '{run_id}' is in status '{current_status}' and cannot accept new uploads.",
            details={"run_id": run_id, "current_status": current_status},
            status_code=409
        )


class RunAlreadySubmittedException(BaseAPIException):
    def __init__(self, run_id: str):
        super().__init__(
            error_code="RUN_ALREADY_SUBMITTED",
            message=f"Run '{run_id}' has already been submitted for processing.",
            status_code=409
        )


class RunHasNoImagesException(BaseAPIException):
    def __init__(self, run_id: str):
        super().__init__(
            error_code="RUN_HAS_NO_IMAGES",
            message=f"Run '{run_id}' has no uploaded images. Upload at least one image before submitting.",
            status_code=400
        )


class RunNotCancellableException(BaseAPIException):
    def __init__(self, run_id: str, current_status: str):
        super().__init__(
            error_code="RUN_NOT_CANCELLABLE",
            message=f"Run '{run_id}' is in status '{current_status}' and cannot be cancelled.",
            details={"run_id": run_id, "current_status": current_status},
            status_code=409
        )


# ──────────────────────────────────────────────
# Phase 1 – Upload-specific exceptions
# ──────────────────────────────────────────────

class EmptyFileException(BaseAPIException):
    def __init__(self, filename: str):
        super().__init__(
            error_code="EMPTY_FILE",
            message=f"File '{filename}' is empty.",
            status_code=400
        )


class FileTooLargeException(BaseAPIException):
    def __init__(self, filename: str, size_mb: float, max_mb: int):
        super().__init__(
            error_code="FILE_TOO_LARGE",
            message=f"File '{filename}' is {size_mb:.1f} MB, exceeding the {max_mb} MB limit.",
            details={"filename": filename, "size_mb": size_mb, "max_mb": max_mb},
            status_code=413
        )


class UnsupportedImageFormatException(BaseAPIException):
    def __init__(self, filename: str, detected_format: str):
        super().__init__(
            error_code="UNSUPPORTED_IMAGE_FORMAT",
            message=f"File '{filename}' has unsupported format '{detected_format}'.",
            details={"filename": filename, "format": detected_format},
            status_code=400
        )


class CorruptedImageFileException(BaseAPIException):
    def __init__(self, filename: str):
        super().__init__(
            error_code="CORRUPTED_IMAGE_FILE",
            message=f"File '{filename}' could not be decoded as a valid image.",
            status_code=400
        )


class MaxImageCountExceededException(BaseAPIException):
    def __init__(self, run_id: str, current_count: int, max_count: int):
        super().__init__(
            error_code="MAX_IMAGE_COUNT_EXCEEDED",
            message=f"Run '{run_id}' already has {current_count} images. Maximum allowed is {max_count}.",
            details={"run_id": run_id, "current": current_count, "max": max_count},
            status_code=400
        )


class StorageUploadFailedException(BaseAPIException):
    def __init__(self, filename: str, reason: str = ""):
        super().__init__(
            error_code="STORAGE_UPLOAD_FAILED",
            message=f"Failed to upload file '{filename}' to object storage.",
            details={"filename": filename, "reason": reason},
            status_code=500
        )


class QueueEnqueueFailedException(BaseAPIException):
    def __init__(self, run_id: str, reason: Optional[str] = None):
        msg = (
            f"Failed to enqueue processing job for run '{run_id}'. "
            "Ensure Redis is running and REDIS_URL is correct."
        )
        if reason:
            msg = f"Failed to enqueue processing job for run '{run_id}': {reason}"
        super().__init__(
            error_code="QUEUE_ENQUEUE_FAILED",
            message=msg,
            details={"run_id": run_id, "reason": reason or ""},
            status_code=503,
        )


# ──────────────────────────────────────────────
# Exception handlers (registered in main.py)
# ──────────────────────────────────────────────

async def global_exception_handler(request: Request, exc: BaseAPIException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "request_id": exc.request_id
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "details": {"error": str(exc)},
            "request_id": str(uuid.uuid4())
        }
    )
