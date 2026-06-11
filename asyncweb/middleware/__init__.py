"""
Middleware system — Chain of Responsibility pattern.

Each middleware wraps the next handler in the chain, forming a pipeline:

    Request → [Middleware A] → [Middleware B] → [Route Handler]
                                                       ↓
    Response ← [Middleware A] ← [Middleware B] ←──────┘

SOLID:
- SRP  : Each middleware does exactly one thing.
- OCP  : New middleware is added without changing existing code.
- LSP  : Any BaseMiddleware can replace another in the chain.
- ISP  : Thin interface (only ``__call__`` required).
- DIP  : Middleware depends on abstractions (Request/Response), not concretions.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from asyncweb.core.request import Request
from asyncweb.core.response import Response


logger = logging.getLogger(__name__)

# The innermost callable that all middleware ultimately wraps.
NextHandler = Callable[[Request], Awaitable[Response]]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseMiddleware(ABC):
    """
    Abstract middleware.

    Concrete subclasses implement :meth:`__call__` and may await *next_handler*
    before or after their own logic.
    """

    @abstractmethod
    async def __call__(
        self, request: Request, next_handler: NextHandler
    ) -> Response:  # pragma: no cover
        ...


# ---------------------------------------------------------------------------
# Built-in middleware implementations
# ---------------------------------------------------------------------------

class LoggingMiddleware(BaseMiddleware):
    """
    Logs every request and its response status + duration (ms).
    """

    async def __call__(
        self, request: Request, next_handler: NextHandler
    ) -> Response:
        start = time.perf_counter()
        response = await next_handler(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %d  (%.1f ms)",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response


class CORSMiddleware(BaseMiddleware):
    """
    Adds Cross-Origin Resource Sharing headers to every response.

    Configuration is provided at construction time, keeping the middleware
    stateless per-request (thread/task-safe).
    """

    def __init__(
        self,
        allow_origins: str = "*",
        allow_methods: str = "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        allow_headers: str = "Content-Type, Authorization",
    ) -> None:
        self._allow_origins = allow_origins
        self._allow_methods = allow_methods
        self._allow_headers = allow_headers

    async def __call__(
        self, request: Request, next_handler: NextHandler
    ) -> Response:
        # Handle CORS preflight
        if request.method == "OPTIONS":
            from asyncweb.core.response import Response as R
            return R(
                status_code=204,
                headers=self._cors_headers(),
            )

        response = await next_handler(request)
        response.headers.update(self._cors_headers())
        return response

    def _cors_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": self._allow_origins,
            "Access-Control-Allow-Methods": self._allow_methods,
            "Access-Control-Allow-Headers": self._allow_headers,
        }


class RequestIDMiddleware(BaseMiddleware):
    """
    Injects a unique ``X-Request-ID`` header into every response.
    Useful for distributed tracing.
    """

    async def __call__(
        self, request: Request, next_handler: NextHandler
    ) -> Response:
        import uuid
        request_id = request.get_header("x-request-id") or str(uuid.uuid4())
        response = await next_handler(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Middleware pipeline builder
# ---------------------------------------------------------------------------

class MiddlewarePipeline:
    """
    Assembles a list of :class:`BaseMiddleware` instances into a single
    callable that chains them in order.

    Usage::

        pipeline = MiddlewarePipeline([LoggingMiddleware(), CORSMiddleware()])
        final_handler = pipeline.build(route_handler)
        response = await final_handler(request)
    """

    def __init__(self, middlewares: list[BaseMiddleware]) -> None:
        self._middlewares = middlewares

    def build(self, endpoint: NextHandler) -> NextHandler:
        """
        Wrap *endpoint* with all registered middleware (last registered
        is outermost — i.e. executes first on the way in).
        """
        handler = endpoint
        for middleware in reversed(self._middlewares):
            # Capture the current handler in a closure to avoid late-binding
            handler = self._wrap(middleware, handler)
        return handler

    @staticmethod
    def _wrap(
        middleware: BaseMiddleware, next_handler: NextHandler
    ) -> NextHandler:
        async def wrapped(request: Request) -> Response:
            return await middleware(request, next_handler)
        return wrapped
