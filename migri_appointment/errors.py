class MigriError(Exception):
    """Base error for migri_appointment."""


class UnsupportedOfficeError(MigriError):
    """Raised when office name is not supported."""


class MigriApiError(MigriError):
    """Raised for unexpected API responses."""
