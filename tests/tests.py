"""
tests.py — unit and integration tests for AsyncWeb.

Run:
    python tests.py
"""

from asyncweb.core.server import Application
from asyncweb.routing.router import Router
from asyncweb.middleware import (
    CORSMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
    RequestIDMiddleware,
)
from asyncweb.exceptions import (
    BadRequestException,
    NotFoundException,
    MethodNotAllowedException,
)
from asyncweb.core.response import Response, ResponseFactory
from asyncweb.core.request import Request, RequestParser
import asyncio
import json
import sys
import os
import unittest


def run(coro):
    """Helper to run a coroutine in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# RequestParser tests
# ---------------------------------------------------------------------------

class TestRequestParser(unittest.TestCase):
    def setUp(self):
        self.parser = RequestParser()

    def test_simple_get(self):
        raw = b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n"
        req = self.parser.parse(raw)
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.path, "/health")
        self.assertEqual(req.body, b"")

    def test_post_with_body(self):
        body = b'{"name": "Alice"}'
        raw = (
            b"POST /users HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )
        req = self.parser.parse(raw)
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.json(), {"name": "Alice"})

    def test_query_params(self):
        raw = b"GET /search?q=hello&limit=10 HTTP/1.1\r\n\r\n"
        req = self.parser.parse(raw)
        self.assertEqual(req.query_params["q"], "hello")
        self.assertEqual(req.query_params["limit"], "10")

    def test_malformed_request_line_raises(self):
        raw = b"BADREQUEST\r\n\r\n"
        with self.assertRaises(ValueError):
            self.parser.parse(raw)

    def test_case_insensitive_header(self):
        raw = b"GET / HTTP/1.1\r\nContent-Type: application/json\r\n\r\n"
        req = self.parser.parse(raw)
        self.assertEqual(req.get_header("content-type"), "application/json")
        self.assertEqual(req.get_header("Content-Type"), "application/json")


# ---------------------------------------------------------------------------
# Response / ResponseFactory tests
# ---------------------------------------------------------------------------

class TestResponse(unittest.TestCase):
    def test_json_response(self):
        resp = ResponseFactory.json({"ok": True})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'"ok"', resp.body)
        self.assertIn("application/json", resp.headers["Content-Type"])

    def test_error_response(self):
        resp = ResponseFactory.error(404, "Not Found")
        self.assertEqual(resp.status_code, 404)
        payload = json.loads(resp.body)
        self.assertEqual(payload["error"], "Not Found")

    def test_no_content(self):
        resp = ResponseFactory.no_content()
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.body, b"")

    def test_to_bytes_contains_status_line(self):
        resp = ResponseFactory.json({"x": 1})
        raw = resp.to_bytes()
        self.assertTrue(raw.startswith(b"HTTP/1.1 200 OK\r\n"))

    def test_to_bytes_contains_content_length(self):
        resp = ResponseFactory.json({"x": 1})
        raw = resp.to_bytes().decode()
        self.assertIn("Content-Length:", raw)

    def test_custom_status_code(self):
        resp = ResponseFactory.json({"created": True}, status_code=201)
        self.assertEqual(resp.status_code, 201)
        self.assertIn(b"HTTP/1.1 201 Created", resp.to_bytes())


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------

class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_exact_match(self):
        async def handler(r): pass
        self.router.add_route("GET", "/ping", handler)
        result = self.router.resolve("GET", "/ping")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], handler)

    def test_path_params(self):
        async def handler(r): pass
        self.router.add_route("GET", "/users/{user_id}", handler)
        result = self.router.resolve("GET", "/users/42")
        self.assertIsNotNone(result)
        self.assertEqual(result[1], {"user_id": "42"})

    def test_method_mismatch_returns_none(self):
        async def handler(r): pass
        self.router.add_route("GET", "/ping", handler)
        result = self.router.resolve("POST", "/ping")
        self.assertIsNone(result)

    def test_path_exists(self):
        async def handler(r): pass
        self.router.add_route("GET", "/ping", handler)
        self.assertTrue(self.router.path_exists("/ping"))
        self.assertFalse(self.router.path_exists("/nope"))

    def test_decorator_registration(self):
        router = Router()

        @router.get("/test")
        async def h(r): pass

        result = router.resolve("GET", "/test")
        self.assertIsNotNone(result)

    def test_nested_path_params(self):
        async def handler(r): pass
        self.router.add_route("GET", "/orgs/{org}/repos/{repo}", handler)
        result = self.router.resolve("GET", "/orgs/acme/repos/api")
        self.assertIsNotNone(result)
        self.assertEqual(result[1], {"org": "acme", "repo": "api"})

    def test_registered_routes_introspection(self):
        async def handler(r): pass
        self.router.add_route("POST", "/items", handler)
        routes = self.router.registered_routes()
        self.assertEqual(routes[0], {"method": "POST", "path": "/items"})


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------

class TestMiddleware(unittest.TestCase):
    def _make_request(self, method="GET", path="/"):
        return Request(method=method, path=path)

    def test_cors_headers_added(self):
        async def base(req):
            return ResponseFactory.json({})

        cors = CORSMiddleware()
        pipeline = MiddlewarePipeline([cors])
        handler = pipeline.build(base)
        resp = run(handler(self._make_request()))
        self.assertIn("Access-Control-Allow-Origin", resp.headers)

    def test_cors_options_preflight(self):
        async def base(req):
            return ResponseFactory.json({})

        cors = CORSMiddleware()
        pipeline = MiddlewarePipeline([cors])
        handler = pipeline.build(base)
        resp = run(handler(self._make_request(method="OPTIONS")))
        self.assertEqual(resp.status_code, 204)

    def test_request_id_injected(self):
        async def base(req):
            return ResponseFactory.json({})

        mid = RequestIDMiddleware()
        pipeline = MiddlewarePipeline([mid])
        handler = pipeline.build(base)
        resp = run(handler(self._make_request()))
        self.assertIn("X-Request-ID", resp.headers)

    def test_logging_middleware_passes_through(self):
        async def base(req):
            return ResponseFactory.json({"ok": True})

        mid = LoggingMiddleware()
        pipeline = MiddlewarePipeline([mid])
        handler = pipeline.build(base)
        resp = run(handler(self._make_request()))
        self.assertEqual(resp.status_code, 200)

    def test_middleware_order(self):
        """Verify middleware executes in registration order (first = outermost)."""
        order = []

        from asyncweb.middleware import BaseMiddleware

        class TracingMid(BaseMiddleware):
            def __init__(self, label):
                self.label = label

            async def __call__(self, req, nxt):
                order.append(f"before-{self.label}")
                r = await nxt(req)
                order.append(f"after-{self.label}")
                return r

        async def base(req):
            order.append("handler")
            return ResponseFactory.json({})

        pipeline = MiddlewarePipeline([TracingMid("A"), TracingMid("B")])
        run(pipeline.build(base)(Request(method="GET", path="/")))
        self.assertEqual(order, [
            "before-A", "before-B", "handler", "after-B", "after-A"
        ])


# ---------------------------------------------------------------------------
# Application dispatch tests
# ---------------------------------------------------------------------------

class TestApplication(unittest.TestCase):
    def setUp(self):
        self.app = Application()

    def _req(self, method, path, body=b""):
        return Request(method=method, path=path, body=body)

    def test_dispatch_found(self):
        @self.app.router.get("/ping")
        async def ping(req):
            return ResponseFactory.json({"pong": True})

        resp = run(self.app.dispatch(self._req("GET", "/ping")))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"pong", resp.body)

    def test_dispatch_404(self):
        resp = run(self.app.dispatch(self._req("GET", "/missing")))
        self.assertEqual(resp.status_code, 404)

    def test_dispatch_405(self):
        @self.app.router.get("/only-get")
        async def h(req):
            return ResponseFactory.json({})

        resp = run(self.app.dispatch(self._req("POST", "/only-get")))
        self.assertEqual(resp.status_code, 405)

    def test_handler_http_exception_forwarded(self):
        @self.app.router.get("/boom")
        async def boom(req):
            raise NotFoundException("gone")

        resp = run(self.app.dispatch(self._req("GET", "/boom")))
        self.assertEqual(resp.status_code, 404)

    def test_handler_unhandled_exception_returns_500(self):
        @self.app.router.get("/crash")
        async def crash(req):
            raise RuntimeError("oops")

        resp = run(self.app.dispatch(self._req("GET", "/crash")))
        self.assertEqual(resp.status_code, 500)

    def test_path_params_injected(self):
        @self.app.router.get("/items/{item_id}")
        async def get_item(req):
            return ResponseFactory.json({"id": req.path_params["item_id"]})

        resp = run(self.app.dispatch(self._req("GET", "/items/99")))
        payload = json.loads(resp.body)
        self.assertEqual(payload["id"], "99")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestRequestParser,
        TestResponse,
        TestRouter,
        TestMiddleware,
        TestApplication,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
