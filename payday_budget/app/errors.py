"""Domain errors, rendered as JSON `{code, message, field?}` (§6.4)."""


class ApiError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict[str, str]:
        body = {"code": self.code, "message": self.message}
        if self.field is not None:
            body["field"] = self.field
        return body


class RuleViolation(ApiError):
    """A §5 business rule was violated; `code` is the rule ID."""

    status_code = 422


class NotFound(ApiError):
    status_code = 404

    def __init__(self, what: str, field: str | None = None) -> None:
        super().__init__("not_found", f"{what} not found", field)


class Forbidden(ApiError):
    status_code = 403

    def __init__(self, message: str) -> None:
        super().__init__("forbidden", message)


class Conflict(ApiError):
    status_code = 409

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__("conflict", message, field)


class InvalidInput(ApiError):
    status_code = 422

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__("validation_error", message, field)
