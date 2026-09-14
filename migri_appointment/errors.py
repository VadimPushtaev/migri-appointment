class MigriError(Exception):
    """Base error for migri_appointment."""


class UnsupportedOfficeError(MigriError):
    """Raised when office name is not supported."""


class MigriApiError(MigriError):
    """Raised for unexpected API responses."""


class MigriForbiddenError(MigriApiError):
    """Raised when Migri rejects a request with HTTP 403."""
