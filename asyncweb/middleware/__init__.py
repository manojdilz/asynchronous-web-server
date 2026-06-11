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

from asyncweb.middleware.base_middleware import BaseMiddleware
from asyncweb.middleware.cors_middleware import CORSMiddleware
from asyncweb.middleware.logging_middleware import LoggingMiddleware
from asyncweb.middleware.request_id_middleware import RequestIDMiddleware
from asyncweb.middleware.middleware_pipeline import MiddlewarePipeline


__all__ = [
    "BaseMiddleware",
    "CORSMiddleware",
    "LoggingMiddleware",
    "RequestIDMiddleware",
    "MiddlewarePipeline",
]
