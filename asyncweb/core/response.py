"""
HTTP Response model + ResponseFactory.

ResponseFactory (Factory Pattern) centralises how responses are built,
so callers never construct raw bytes manually.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

@dataclass
class Response:
    """
    Represents an outgoing HTTP/1.1 response.

    Attributes:
        status_code: Numeric HTTP status (200, 404, …).
        body:        Response payload as bytes.
        headers:     Dict of response headers (values are always strings).
    """

    status_code: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    # Human-readable phrases for common status codes
    _PHRASES: dict[int, str] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_PHRASES", {
            200: "OK",
            201: "Created",
            204: "No Content",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
            422: "Unprocessable Entity",
            500: "Internal Server Error",
        })

    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the response to a valid HTTP/1.1 wire format."""
        phrase = self._PHRASES.get(self.status_code, "Unknown")
        status_line = f"HTTP/1.1 {self.status_code} {phrase}\r\n"

        # Always include Content-Length so the client knows when to stop reading
        all_headers = {
            "Content-Length": str(len(self.body)),
            "Connection": "close",
            **self.headers,
        }
        header_block = "".join(
            f"{k}: {v}\r\n" for k, v in all_headers.items()
        )
        return (status_line + header_block + "\r\n").encode() + self.body

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Response {self.status_code} ({len(self.body)} bytes)>"


# ---------------------------------------------------------------------------
# Factory (Factory Pattern) — open/closed: add new factory methods without
# touching existing ones.
# ---------------------------------------------------------------------------

class ResponseFactory:
    """
    Centralised factory for building :class:`Response` objects.

    All JSON responses share the same Content-Type header and encoding
    logic, keeping callers free of boilerplate.
    """

    _JSON_CONTENT_TYPE = "application/json; charset=utf-8"

    @classmethod
    def json(
        cls,
        data: Any,
        *,
        status_code: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> Response:
        """Return a JSON-encoded response."""
        body = json.dumps(data, ensure_ascii=False,
                          default=str).encode("utf-8")
        headers = {"Content-Type": cls._JSON_CONTENT_TYPE}
        if extra_headers:
            headers.update(extra_headers)
        return Response(status_code=status_code, body=body, headers=headers)

    @classmethod
    def error(cls, status_code: int, detail: str) -> Response:
        """Return a JSON error response."""
        return cls.json(
            {"error": detail, "status_code": status_code},
            status_code=status_code,
        )

    @classmethod
    def no_content(cls) -> Response:
        """Return an empty 204 response."""
        return Response(status_code=204)
