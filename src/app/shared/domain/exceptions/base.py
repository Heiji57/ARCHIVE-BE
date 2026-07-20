class BaseAppException(Exception):
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "",
        details: list[dict] | None = None,
    ) -> None:
        self.message = message
        self.details = details or []
        super().__init__(message)
