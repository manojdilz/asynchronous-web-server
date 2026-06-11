from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from asyncweb.core.request import Request
from asyncweb.core.response import Response


# The innermost callable that all middleware ultimately wraps.
NextHandler = Callable[[Request], Awaitable[Response]]


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
