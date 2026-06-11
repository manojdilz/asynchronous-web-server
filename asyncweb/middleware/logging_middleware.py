import logging
import time

from asyncweb.core.request import Request
from asyncweb.core.response import Response
from asyncweb.middleware.base_middleware import BaseMiddleware, NextHandler

logger = logging.getLogger(__name__)


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
