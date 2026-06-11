"""
Router — maps (method, path) pairs to async handler callables.

Design patterns used:
- Strategy   : each route handler is a pluggable async callable.
- Template   : _match() defines the algorithm; subclasses could override.

SOLID:
- SRP : Router only resolves routes; it does not execute handlers.
- OCP : New routes are added via .add_route() without touching existing code.
- DIP : Handlers depend on the Request/Response abstractions, not on raw bytes.
"""

from __future__ import annotations

import re
from typing import Awaitable, Callable

from asyncweb.core.request import Request
from asyncweb.core.response import Response
from asyncweb.routing.route import Route

# A handler is any async callable: async def handler(req: Request) -> Response
HandlerType = Callable[[Request], Awaitable[Response]]


class Router:
    """
    Lightweight URL router that supports:
    - Exact path matching  : ``/health``
    - Path parameters      : ``/users/{user_id}``

    Matching is performed in registration order; the first match wins.
    """

    # Regex that recognises ``{param_name}`` placeholders
    _PARAM_RE = re.compile(r"\{(\w+)\}")

    def __init__(self) -> None:
        self._routes: list[Route] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_route(
        self, method: str, path: str, handler: HandlerType
    ) -> None:
        """
        Register *handler* for ``METHOD path``.

        Path parameters are expressed as ``{name}`` and will be injected
        into ``Request.path_params`` on a successful match.

        Example::

            router.add_route("GET", "/users/{user_id}", get_user_handler)
        """
        pattern, param_names = self._compile(path)
        self._routes.append(
            Route(
                method=method.upper(),
                pattern=pattern,
                param_names=param_names,
                handler=handler,
                raw_path=path,
            )
        )

    # Convenience decorators ------------------------------------------------

    def get(self, path: str) -> Callable[[HandlerType], HandlerType]:
        return self._decorator("GET", path)

    def post(self, path: str) -> Callable[[HandlerType], HandlerType]:
        return self._decorator("POST", path)

    def put(self, path: str) -> Callable[[HandlerType], HandlerType]:
        return self._decorator("PUT", path)

    def patch(self, path: str) -> Callable[[HandlerType], HandlerType]:
        return self._decorator("PATCH", path)

    def delete(self, path: str) -> Callable[[HandlerType], HandlerType]:
        return self._decorator("DELETE", path)

    def _decorator(
        self, method: str, path: str
    ) -> Callable[[HandlerType], HandlerType]:
        def wrapper(handler: HandlerType) -> HandlerType:
            self.add_route(method, path, handler)
            return handler
        return wrapper

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self, method: str, path: str
    ) -> tuple[HandlerType, dict[str, str]] | None:
        """
        Return ``(handler, path_params)`` for the first matching route,
        or ``None`` if no route matches at all.

        Callers should separately check whether the path matches but the
        method does not (405 vs 404).
        """
        method = method.upper()
        for route in self._routes:
            match = route.pattern.fullmatch(path)
            if match:
                if route.method == method:
                    params = dict(zip(route.param_names, match.groups()))
                    return route.handler, params
        return None

    def path_exists(self, path: str) -> bool:
        """Return True if *any* method is registered for *path*."""
        for route in self._routes:
            if route.pattern.fullmatch(path):
                return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _compile(cls, path: str) -> tuple[re.Pattern, list[str]]:
        """
        Convert a path template like ``/users/{user_id}`` into a compiled
        regex and the ordered list of parameter names.
        """
        param_names: list[str] = []

        def replacer(m: re.Match) -> str:
            param_names.append(m.group(1))
            return r"([^/]+)"

        escaped = re.escape(path)
        # re.escape will have escaped the braces; undo that for our placeholders
        escaped = escaped.replace(r"\{", "{").replace(r"\}", "}")
        pattern_str = cls._PARAM_RE.sub(replacer, escaped)
        return re.compile(pattern_str), param_names

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def registered_routes(self) -> list[dict]:
        return [
            {"method": r.method, "path": r.raw_path}
            for r in self._routes
        ]
