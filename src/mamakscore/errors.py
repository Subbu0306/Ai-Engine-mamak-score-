"""Stable, non-sensitive service errors."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNREADABLE_PDF = "UNREADABLE_PDF"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    VISION_REQUIRED = "VISION_REQUIRED"
    UNREADABLE_WORKBOOK = "UNREADABLE_WORKBOOK"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    UNGROUNDED_EVIDENCE = "UNGROUNDED_EVIDENCE"
    OVER_CAPACITY = "OVER_CAPACITY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ServiceError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        field: str | None = None,
        retryable: bool = False,
        status_code: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.retryable = retryable
        self.status_code = status_code
        self.details = details or {}
