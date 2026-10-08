"""Standardized error codes and exceptions for MamakScore AI Engine."""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    # Request & file payload errors
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNREADABLE_PDF = "UNREADABLE_PDF"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    VISION_REQUIRED = "VISION_REQUIRED"
    UNREADABLE_WORKBOOK = "UNREADABLE_WORKBOOK"
    ZIP_BOMB_DETECTED = "ZIP_BOMB_DETECTED"

    # Business domain and model contract errors
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    UNGROUNDED_EVIDENCE = "UNGROUNDED_EVIDENCE"
    APPLICATION_MISMATCH = "APPLICATION_MISMATCH"
    RUBRIC_VERSION_MISMATCH = "RUBRIC_VERSION_MISMATCH"

    # Operational & capacity errors
    OVER_CAPACITY = "OVER_CAPACITY"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ServiceError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.field:
            result["field"] = self.field
        if self.details:
            result["details"] = self.details
        return result