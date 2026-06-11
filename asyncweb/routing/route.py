from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from asyncweb.core.request import Request
from asyncweb.core.response import Response

HandlerType = Callable[[Request], Awaitable[Response]]


@dataclass
class Route:
    """
    Stores a single registered route.

    Attributes:
        method:   HTTP verb (upper-cased).
        pattern:  Compiled regex pattern derived from the path template.
        param_names: Named path parameters extracted from the template
                     (e.g. ``["user_id"]`` for ``/users/{user_id}``).
        handler:  Async callable to invoke on a match.
        raw_path: Original path template string (for introspection / docs).
    """

    method: str
    pattern: re.Pattern
    param_names: list[str]
    handler: HandlerType
    raw_path: str
