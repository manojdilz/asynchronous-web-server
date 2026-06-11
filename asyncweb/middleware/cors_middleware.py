import logging

from asyncweb.core.request import Request
from asyncweb.core.response import Response
from asyncweb.middleware.base_middleware import BaseMiddleware, NextHandler
from asyncweb.core.response import Response


logger = logging.getLogger(__name__)


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
            return Response(
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
