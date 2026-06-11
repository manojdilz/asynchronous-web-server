"""
Immutable HTTP Request model.
Parsed once from raw bytes; read-only after construction.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Request:
    """
    Represents a parsed HTTP/1.1 request.

    Attributes:
        method:      HTTP verb (GET, POST, …) — always upper-cased.
        path:        URL path without query string (e.g. "/users/42").
        query_params: Parsed query-string key/value pairs.
        headers:     Case-insensitive header dict (lowercased keys).
        body:        Raw request body bytes.
        path_params: Route placeholders injected by the router.
    """

    method: str
    path: str
    query_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    path_params: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Body helpers
    # ------------------------------------------------------------------

    def json(self) -> Any:
        """Decode body as JSON. Raises ValueError on malformed input."""
        return json.loads(self.body)

    def text(self) -> str:
        """Decode body as UTF-8 text."""
        return self.body.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_header(self, name: str, default: str = "") -> str:
        """Case-insensitive header lookup."""
        return self.headers.get(name.lower(), default)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Request {self.method} {self.path}>"


# ---------------------------------------------------------------------------
# Parser (Single Responsibility: only knows about raw HTTP bytes → Request)
# ---------------------------------------------------------------------------

class RequestParser:
    """
    Parses a raw HTTP/1.1 request from bytes into a :class:`Request`.

    Keeps state to handle chunked reads from the TCP stream.
    """

    _MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    def parse(self, raw: bytes) -> Request:
        """
        Parse *raw* HTTP request bytes.

        Raises:
            ValueError: if the request line is malformed.
        """
        header_section, _, body = raw.partition(b"\r\n\r\n")
        lines = header_section.decode("utf-8", errors="replace").split("\r\n")

        method, path_with_qs, _http_version = self._parse_request_line(
            lines[0])
        path, query_params = self._split_path(path_with_qs)
        headers = self._parse_headers(lines[1:])

        content_length = int(headers.get("content-length", "0"))
        body = body[:min(content_length, self._MAX_BODY_SIZE)]

        return Request(
            method=method,
            path=path,
            query_params=query_params,
            headers=headers,
            body=body,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_request_line(line: str) -> tuple[str, str, str]:
        parts = line.strip().split(" ", 2)
        if len(parts) != 3:
            raise ValueError(f"Malformed request line: {line!r}")
        method, path, version = parts
        return method.upper(), path, version

    @staticmethod
    def _split_path(path_with_qs: str) -> tuple[str, dict[str, str]]:
        if "?" in path_with_qs:
            path, qs = path_with_qs.split("?", 1)
            params = dict(urllib.parse.parse_qsl(qs))
        else:
            path, params = path_with_qs, {}
        return path, params

    @staticmethod
    def _parse_headers(lines: list[str]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in lines:
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        return headers
