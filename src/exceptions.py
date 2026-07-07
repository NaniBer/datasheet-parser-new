"""
Custom exception types for Datasheet Parser.

Provides specific exception classes for different error types,
enabling better error handling, retry logic, and user feedback.
"""


class DatasheetParserError(Exception):
    """Base exception for all datasheet parser errors."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        """
        Initialize exception with optional error code and details.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for programmatic handling
            details: Additional context about the error
        """
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class PageDetectionError(DatasheetParserError):
    """Errors during page detection phase."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "PAGE_DETECTION_ERROR"


class ContentExtractionError(DatasheetParserError):
    """Errors during content extraction phase."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "CONTENT_EXTRACTION_ERROR"


class LLMExtractionError(DatasheetParserError):
    """Errors during LLM pin data extraction phase."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "LLM_EXTRACTION_ERROR"

    @property
    def is_retryable(self) -> bool:
        """
        Check if this error is retryable.

        Returns:
            True if error is retryable (network, timeout, rate limit), False otherwise
        """
        if not self.details:
            return False

        # Retryable error conditions
        error_message = str(self).lower()
        return (
            "timeout" in error_message or
            "connection" in error_message or
            "network" in error_message or
            "rate limit" in error_message or
            "429" in error_message or  # HTTP 429 - Too Many Requests
            "500" in error_message or  # HTTP 500 - Server Error
            "502" in error_message or  # HTTP 502 - Bad Gateway
            "503" in error_message or  # HTTP 503 - Service Unavailable
            "504" in error_message    # HTTP 504 - Gateway Timeout
        )


class SchematicGenerationError(DatasheetParserError):
    """Errors during schematic generation phase."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "SCHEMATIC_GENERATION_ERROR"


class ValidationError(DatasheetParserError):
    """Errors during input validation."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "VALIDATION_ERROR"


class FileError(DatasheetParserError):
    """Errors related to file operations (reading PDF, writing output, etc.)."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "FILE_ERROR"


class APICredentialsError(DatasheetParserError):
    """Errors related to API key or credentials."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message, error_code, details)
        self.error_code = error_code or "API_CREDENTIALS_ERROR"


# ============================================================================
# Error Codes
# ============================================================================

class ErrorCodes:
    """Machine-readable error codes for programmatic error handling."""

    # Page Detection
    NO_RELEVANT_PAGES = "PAGE_NO_RELEVANT_PAGES"
    PDF_OPEN_FAILED = "PAGE_PDF_OPEN_FAILED"

    # Content Extraction
    EXTRACTION_FAILED = "CONTENT_EXTRACTION_FAILED"
    NO_PAGES_FOUND = "CONTENT_NO_PAGES_FOUND"

    # LLM Extraction
    LLM_API_ERROR = "LLM_API_ERROR"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_CONNECTION_ERROR = "LLM_CONNECTION_ERROR"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"

    # Schematic Generation
    PACKAGE_UNKNOWN = "SCHEMATIC_PACKAGE_UNKNOWN"
    BUILD_FAILED = "SCHEMATIC_BUILD_FAILED"
    EXPORT_FAILED = "SCHEMATIC_EXPORT_FAILED"

    # Validation
    INVALID_INPUT_FILE = "VALIDATION_INVALID_INPUT_FILE"
    INVALID_OUTPUT_PATH = "VALIDATION_INVALID_OUTPUT_PATH"
    INVALID_PDF_FILE = "VALIDATION_INVALID_PDF_FILE"
    EXTRACTION_VALIDATION_FAILED = "VALIDATION_EXTRACTION_FAILED"

    # File Operations
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_FAILED = "FILE_READ_FAILED"
    FILE_WRITE_FAILED = "FILE_WRITE_FAILED"

    # API Credentials
    MISSING_API_KEY = "API_MISSING_API_KEY"
    INVALID_API_KEY = "API_INVALID_API_KEY"
