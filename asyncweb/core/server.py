"""
AsyncServer — raw asyncio TCP server.
 
Responsibilities (SRP — one per class):
- ConnectionHandler  : reads one HTTP request, writes one response.
- Application        : wires router + middleware; top-level façade.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import signal
from typing import TYPE_CHECKING

from asyncweb.core.request import Request, RequestParser
from asyncweb.core.response import Response, ResponseFactory
from asyncweb.exceptions import (
    HTTPException,
    MethodNotAllowedException,
    NotFoundException,
)
from asyncweb.middleware import BaseMiddleware, MiddlewarePipeline
from asyncweb.routing.router import Router

logger = logging.getLogger(__name__)

_READ_CHUNK = 65536   # 64 KB per read
_READ_TIMEOUT = 30.0  # seconds
_IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Connection handler  (SRP: one HTTP exchange)
# ---------------------------------------------------------------------------

class ConnectionHandler:
    """
    Handles a single client TCP connection: read → parse → dispatch → write.

    Each connection is isolated; no shared mutable state between coroutines.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        dispatch,
        parser: RequestParser,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._dispatch = dispatch
        self._parser = parser

    async def handle(self) -> None:
        peer = self._writer.get_extra_info("peername")
        response = ResponseFactory.error(500, "Internal Server Error")
        try:
            raw = await asyncio.wait_for(
                self._read_request(), timeout=_READ_TIMEOUT
            )
            if not raw:
                return
            request = self._parser.parse(raw)
            response = await self._dispatch(request)

        except asyncio.TimeoutError:
            logger.warning("Read timeout from %s", peer)
            response = ResponseFactory.error(408, "Request Timeout")
        except ValueError as exc:
            logger.warning("Bad request from %s: %s", peer, exc)
            response = ResponseFactory.error(400, str(exc))
        except Exception:
            logger.exception("Unhandled error for connection from %s", peer)
        finally:
            try:
                self._writer.write(response.to_bytes())
                await self._writer.drain()
            except Exception:
                pass
            self._writer.close()

    async def _read_request(self) -> bytes:
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = await self._reader.read(_READ_CHUNK)
            if not chunk:
                break
            raw += chunk

        header_part, _, body_start = raw.partition(b"\r\n\r\n")
        content_length = 0
        for line in header_part.split(b"\r\n")[1:]:
            if line.lower().startswith(b"content-length:"):
                try:
                    content_length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    pass
                break

        remaining = content_length - len(body_start)
        while remaining > 0:
            chunk = await self._reader.read(min(_READ_CHUNK, remaining))
            if not chunk:
                break
            raw += chunk
            remaining -= len(chunk)

        return raw


# ---------------------------------------------------------------------------
# Application  (Façade)
# ---------------------------------------------------------------------------

class Application:
    """
    Top-level application object.

    Usage::

        app = Application()

        @app.router.get("/ping")
        async def ping(req):
            return ResponseFactory.json({"pong": True})

        app.add_middleware(LoggingMiddleware())
        asyncio.run(app.run())
    """

    def __init__(self) -> None:
        self.router = Router()
        self._middlewares: list[BaseMiddleware] = []
        self._parser = RequestParser()

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        """Append middleware to the pipeline (first added = outermost)."""
        self._middlewares.append(middleware)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request) -> Response:
        pipeline = MiddlewarePipeline(self._middlewares)
        wrapped = pipeline.build(self._route_handler)
        return await wrapped(request)

    async def _route_handler(self, request: Request) -> Response:
        try:
            result = self.router.resolve(request.method, request.path)
            if result is None:
                if self.router.path_exists(request.path):
                    raise MethodNotAllowedException()
                raise NotFoundException()

            handler, path_params = result
            enriched = Request(
                method=request.method,
                path=request.path,
                query_params=request.query_params,
                headers=request.headers,
                body=request.body,
                path_params=path_params,
            )
            return await handler(enriched)

        except HTTPException as exc:
            return ResponseFactory.error(exc.status_code, exc.detail)
        except Exception:
            logger.exception(
                "Unhandled exception in handler for %s %s",
                request.method, request.path,
            )
            return ResponseFactory.error(500, "Internal Server Error")

    # ------------------------------------------------------------------
    # Server lifecycle — cross-platform shutdown
    # ------------------------------------------------------------------

    async def run(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """
        Serve forever; stop cleanly on Ctrl+C (all platforms) or SIGTERM (Unix).

        Windows note: ``asyncio`` on Windows does not support
        ``loop.add_signal_handler()``, so we rely solely on
        ``KeyboardInterrupt`` propagating through ``asyncio.run()``.
        """
        server = await asyncio.start_server(self._handle_connection, host, port)
        addr = server.sockets[0].getsockname()
        logger.info("🚀  AsyncWeb listening on http://%s:%d", addr[0], addr[1])
        logger.info("Press Ctrl+C to stop.")

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        # SIGTERM: available on Unix/macOS only
        if not _IS_WINDOWS:
            try:
                loop.add_signal_handler(signal.SIGTERM, stop_event.set)
            except (NotImplementedError, AttributeError):
                pass

        async with server:
            if _IS_WINDOWS:
                # On Windows, asyncio.run() raises KeyboardInterrupt from
                # outside the loop when Ctrl+C is pressed.  We just keep
                # serving; the interrupt will bubble up and exit cleanly.
                await _serve_forever_windows(stop_event)
            else:
                await stop_event.wait()

        logger.info("Server shut down gracefully.")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        handler = ConnectionHandler(
            reader=reader,
            writer=writer,
            dispatch=self.dispatch,
            parser=self._parser,
        )
        await handler.handle()


async def _serve_forever_windows(stop_event: asyncio.Event) -> None:
    """
    Windows-compatible "serve forever" loop.

    Polls the stop_event in short intervals so that a KeyboardInterrupt
    raised by the OS can actually interrupt the coroutine.  Without the
    sleep, ``await stop_event.wait()`` would block the thread entirely and
    Ctrl+C would only take effect after the next I/O wakeup.
    """
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            pass  # still running — check again
