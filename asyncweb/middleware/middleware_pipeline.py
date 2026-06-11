import logging

from asyncweb.core.request import Request
from asyncweb.core.response import Response
from asyncweb.middleware.base_middleware import BaseMiddleware, NextHandler

logger = logging.getLogger(__name__)


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
