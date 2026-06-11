class HTTPException(Exception):
    """Base class for all HTTP exceptions."""

    status_code: int = 500
    default_detail: str = "Internal Server Error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)

    def to_dict(self) -> dict:
        return {"error": self.detail, "status_code": self.status_code}
