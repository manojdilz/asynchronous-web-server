import logging
import uuid

from asyncweb.core.request import Request
from asyncweb.core.response import Response
from asyncweb.middleware.base_middleware import BaseMiddleware, NextHandler

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseMiddleware):
    """
    Injects a unique ``X-Request-ID`` header into every response.
    Useful for distributed tracing.
    """

    async def __call__(
        self, request: Request, next_handler: NextHandler
    ) -> Response:
        request_id = request.get_header("x-request-id") or str(uuid.uuid4())
        response = await next_handler(request)
        response.headers["X-Request-ID"] = request_id
        return response
