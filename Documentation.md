# AsyncWeb — Technical Documentation

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Design patterns](#2-design-patterns)
3. [SOLID principles](#3-solid-principles)
4. [Module reference](#4-module-reference)
   - [Request](#41-request--requestparser)
   - [Response & ResponseFactory](#42-response--responsefactory)
   - [Router](#43-router)
   - [Middleware](#44-middleware)
   - [Exceptions](#45-exceptions)
   - [Application & ConnectionHandler](#46-application--connectionhandler)
5. [Request lifecycle](#5-request-lifecycle)
6. [Routing](#6-routing)
7. [Middleware pipeline](#7-middleware-pipeline)
8. [Error handling](#8-error-handling)
9. [Writing custom middleware](#9-writing-custom-middleware)
10. [Writing route handlers](#10-writing-route-handlers)
11. [Configuration reference](#11-configuration-reference)
12. [Testing guide](#12-testing-guide)
13. [Platform notes](#13-platform-notes)
14. [Extension points](#14-extension-points)

---

## 1. Architecture overview

AsyncWeb is structured as a set of small, focused layers. Each layer only knows about the layer directly below it.

```
┌─────────────────────────────────────────────────────────┐
│                    example_app.py                       │  ← your application code
├─────────────────────────────────────────────────────────┤
│                    Application                          │  ← orchestrator / façade
├───────────────────┬─────────────────────────────────────┤
│     Router        │       MiddlewarePipeline            │  ← routing + middleware
├───────────────────┴─────────────────────────────────────┤
│              Request  /  Response                       │  ← data models
├─────────────────────────────────────────────────────────┤
│           ConnectionHandler  (asyncio TCP)              │  ← transport
└─────────────────────────────────────────────────────────┘
```

**Data flow (one request):**

```
TCP bytes
   │
   ▼
RequestParser.parse()        — raw bytes → Request object
   │
   ▼
MiddlewarePipeline            — chain of pre/post-processing hooks
   │
   ▼
Router.resolve()              — (method, path) → handler + path_params
   │
   ▼
route handler(request)        — your async function → Response
   │
   ▼
Response.to_bytes()           — Response object → TCP bytes
```

**Directory layout:**

```
asyncweb/
│   __init__.py          public API surface
│
├── core/
│   ├── request.py       Request dataclass + RequestParser
│   ├── response.py      Response dataclass + ResponseFactory
│   └── server.py        ConnectionHandler + Application
│
├── routing/
│   └── router.py        URL router (path params, method dispatch)
│
├── middleware/
│   └── __init__.py      BaseMiddleware ABC + 3 built-ins + MiddlewarePipeline
│
└── exceptions/
    └── __init__.py      HTTPException hierarchy
```

---

## 2. Design patterns

### Chain of Responsibility — middleware pipeline

Each middleware receives the request and a reference to the next handler in the chain. It can run logic before calling the next handler (pre-processing), after (post-processing), or both.

```
Request → [LoggingMiddleware] → [CORSMiddleware] → [RequestIDMiddleware] → [route handler]
                                                                                   ↓
Response ← [LoggingMiddleware] ← [CORSMiddleware] ← [RequestIDMiddleware] ←───────┘
```

This means middleware registered **first** is the **outermost** wrapper — it sees the request first and the response last.

### Strategy — route handlers

Every route handler is a pluggable async callable with the signature:

```python
async def handler(request: Request) -> Response: ...
```

Handlers are registered with the router and swapped freely without any changes to the framework. The router stores them as first-class objects.

### Factory — ResponseFactory

`ResponseFactory` centralises all response construction. Callers never build raw bytes or set headers manually:

```python
ResponseFactory.json(data)                        # 200 OK, JSON body
ResponseFactory.json(data, status_code=201)       # 201 Created
ResponseFactory.error(404, "User not found")      # JSON error body
ResponseFactory.no_content()                      # 204 No Content, empty body
```

### Template Method — Router._compile()

`Router._compile()` defines the algorithm for converting a path template string (e.g. `/users/{user_id}`) into a compiled regex and a list of parameter names. Subclasses can override this method to support different path syntaxes.

---

## 3. SOLID principles

| Principle | Applied where |
|---|---|
| **Single Responsibility** | `RequestParser` only parses bytes into a `Request`. `Router` only resolves routes. `ConnectionHandler` only manages one TCP connection. `ResponseFactory` only builds `Response` objects. |
| **Open / Closed** | Add routes with `router.add_route()` or decorators. Add middleware with `app.add_middleware()`. Neither requires changing existing code. |
| **Liskov Substitution** | Any `BaseMiddleware` subclass can replace any other in the pipeline without the pipeline knowing or caring. |
| **Interface Segregation** | `BaseMiddleware` exposes only `__call__`. Route handlers only need to accept a `Request` and return a `Response`. No fat interfaces. |
| **Dependency Inversion** | All layers depend on the `Request` and `Response` abstractions. `ConnectionHandler` receives a `dispatch` callable — it doesn't know about `Application` directly. |

---

## 4. Module reference

### 4.1 Request / RequestParser

**File:** `asyncweb/core/request.py`

#### `Request` (frozen dataclass)

Represents a fully parsed, immutable HTTP request.

| Attribute | Type | Description |
|---|---|---|
| `method` | `str` | HTTP verb, always upper-cased (`GET`, `POST`, …) |
| `path` | `str` | URL path without query string (e.g. `/users/42`) |
| `query_params` | `dict[str, str]` | Parsed query-string key/value pairs |
| `headers` | `dict[str, str]` | Request headers with lower-cased keys |
| `body` | `bytes` | Raw request body (up to 10 MB) |
| `path_params` | `dict[str, str]` | Route placeholders injected by the router |

**Methods:**

```python
request.json() -> Any
```
Decodes the body as JSON. Raises `ValueError` on malformed input.

```python
request.text() -> str
```
Decodes the body as UTF-8 text.

```python
request.get_header(name: str, default: str = "") -> str
```
Case-insensitive header lookup. Returns `default` if the header is absent.

#### `RequestParser`

Parses raw HTTP/1.1 bytes into a `Request`. Used internally by `ConnectionHandler`.

```python
parser = RequestParser()
request = parser.parse(raw_bytes)
```

**Limits:** body capped at 10 MB (`_MAX_BODY_SIZE`).

---

### 4.2 Response / ResponseFactory

**File:** `asyncweb/core/response.py`

#### `Response` (dataclass)

Represents an outgoing HTTP/1.1 response.

| Attribute | Type | Description |
|---|---|---|
| `status_code` | `int` | HTTP status code (default `200`) |
| `body` | `bytes` | Response payload |
| `headers` | `dict[str, str]` | Response headers |

```python
response.to_bytes() -> bytes
```
Serialises the response to valid HTTP/1.1 wire format, including `Content-Length` and `Connection: close` headers.

#### `ResponseFactory`

```python
ResponseFactory.json(data, *, status_code=200, extra_headers=None) -> Response
```
Encodes `data` as JSON with `Content-Type: application/json; charset=utf-8`.

```python
ResponseFactory.error(status_code: int, detail: str) -> Response
```
Returns a JSON body `{"error": "...", "status_code": ...}`.

```python
ResponseFactory.no_content() -> Response
```
Returns an empty `204 No Content` response.

---

### 4.3 Router

**File:** `asyncweb/routing/router.py`

#### Registration

```python
# Imperative
router.add_route("GET", "/users/{user_id}", handler)

# Decorator (preferred)
@router.get("/users/{user_id}")
async def get_user(req): ...

# All supported decorators
@router.get(path)
@router.post(path)
@router.put(path)
@router.patch(path)
@router.delete(path)
```

#### Resolution

```python
result = router.resolve(method, path)
# Returns (handler, path_params) or None
```

```python
router.path_exists(path) -> bool
# True if any method is registered for path (used for 404 vs 405)
```

```python
router.registered_routes() -> list[dict]
# Returns [{"method": "GET", "path": "/users/{user_id}"}, ...]
```

#### Path parameters

Path parameters are defined with `{name}` placeholders and match any non-slash segment:

```
/users/{user_id}          matches /users/42        → {"user_id": "42"}
/orgs/{org}/repos/{repo}  matches /orgs/acme/repos/api → {"org": "acme", "repo": "api"}
```

All path parameter values are **strings**. Cast to the required type in your handler:

```python
user_id = int(req.path_params["user_id"])
```

---

### 4.4 Middleware

**File:** `asyncweb/middleware/__init__.py`

#### `BaseMiddleware` (abstract)

```python
class BaseMiddleware(ABC):
    @abstractmethod
    async def __call__(self, request: Request, next_handler: NextHandler) -> Response:
        ...
```

#### Built-in middleware

**`LoggingMiddleware`**
Logs `METHOD /path → STATUS_CODE (X.X ms)` for every request using Python's standard `logging` module.

**`CORSMiddleware`**
Adds CORS headers to every response. Handles `OPTIONS` preflight requests automatically with a `204` response.

```python
CORSMiddleware(
    allow_origins="*",
    allow_methods="GET, POST, PUT, PATCH, DELETE, OPTIONS",
    allow_headers="Content-Type, Authorization",
)
```

**`RequestIDMiddleware`**
Injects `X-Request-ID` into every response. If the incoming request already has an `X-Request-ID` header, that value is echoed back; otherwise a new UUID4 is generated.

#### `MiddlewarePipeline`

Assembles a list of middleware into a single callable. Used internally by `Application`.

```python
pipeline = MiddlewarePipeline([LoggingMiddleware(), CORSMiddleware()])
wrapped_handler = pipeline.build(route_handler)
response = await wrapped_handler(request)
```

---

### 4.5 Exceptions

**File:** `asyncweb/exceptions/__init__.py`

All exceptions inherit from `HTTPException`. When raised inside a handler (or the router), `Application._route_handler` catches them and converts them to the appropriate JSON error response automatically.

| Class | Status code | Default message |
|---|---|---|
| `HTTPException` | 500 | Internal Server Error |
| `BadRequestException` | 400 | Bad Request |
| `NotFoundException` | 404 | Not Found |
| `MethodNotAllowedException` | 405 | Method Not Allowed |
| `InternalServerError` | 500 | Internal Server Error |

```python
raise NotFoundException("User 42 not found.")
# → HTTP 404 {"error": "User 42 not found.", "status_code": 404}
```

**Adding a custom exception:**

```python
from asyncweb.exceptions import HTTPException

class UnauthorizedException(HTTPException):
    status_code = 401
    default_detail = "Unauthorized"
```

---

### 4.6 Application / ConnectionHandler

**File:** `asyncweb/core/server.py`

#### `Application`

The top-level façade. Owns the router and middleware list.

```python
app = Application()

app.router          # Router instance — register routes here
app.add_middleware(middleware)   # append to pipeline
await app.dispatch(request)     # manually dispatch a Request (useful in tests)
await app.run(host, port)       # start the TCP server
```

**`app.run(host="127.0.0.1", port=8000)`**
Starts the asyncio TCP server and blocks until Ctrl+C (or SIGTERM on Unix).

#### `ConnectionHandler`

Handles a single TCP connection. Created per-connection; no shared state.

1. Reads raw bytes (up to 64 KB per `read()` call, 30 s timeout)
2. Calls `RequestParser.parse()`
3. Calls `Application.dispatch()`
4. Writes `Response.to_bytes()` back to the socket
5. Closes the connection (`Connection: close`)

Not intended to be used directly — managed by `Application`.

---

## 5. Request lifecycle

```
1.  Client opens TCP connection
        │
2.  ConnectionHandler._read_request()
        Reads chunks until \r\n\r\n (headers end)
        Then reads Content-Length more bytes for the body
        │
3.  RequestParser.parse(raw_bytes)
        Splits request line / headers / body
        Builds frozen Request dataclass
        │
4.  Application.dispatch(request)
        Builds MiddlewarePipeline.build(self._route_handler)
        Calls the outermost middleware
        │
5.  Middleware chain (pre-processing)
        e.g. LoggingMiddleware records start time
        e.g. RequestIDMiddleware reads/generates request ID
        │
6.  Application._route_handler(request)
        Router.resolve(method, path) → (handler, path_params)
        Injects path_params into a new Request
        Calls await handler(request)
        │
7.  Your route handler
        Reads request data, performs business logic
        Returns ResponseFactory.json(...)
        │
8.  Middleware chain (post-processing, in reverse)
        e.g. CORSMiddleware adds CORS headers
        e.g. LoggingMiddleware logs status + elapsed time
        │
9.  Response.to_bytes()
        Serialises to HTTP/1.1 wire format
        │
10. ConnectionHandler writes bytes to socket, closes connection
```

---

## 6. Routing

### Exact paths

```python
@app.router.get("/health")
async def health(req):
    return ResponseFactory.json({"status": "ok"})
```

### Path parameters

```python
@app.router.get("/users/{user_id}")
async def get_user(req):
    user_id = int(req.path_params["user_id"])
    ...
```

### Query parameters

```python
# GET /search?q=alice&limit=5
@app.router.get("/search")
async def search(req):
    q = req.query_params.get("q", "")
    limit = int(req.query_params.get("limit", "10"))
    ...
```

### Reading the request body

```python
@app.router.post("/users")
async def create_user(req):
    data = req.json()          # dict from JSON body
    name = data.get("name")
    ...
```

### Returning responses

```python
return ResponseFactory.json({"id": 1})                      # 200
return ResponseFactory.json({"id": 1}, status_code=201)     # 201
return ResponseFactory.no_content()                         # 204
raise NotFoundException("Item not found.")                  # 404
raise BadRequestException("name is required.")              # 400
```

### 404 vs 405

The router distinguishes between:
- Path not found at all → `404 Not Found`
- Path exists but wrong method → `405 Method Not Allowed`

This happens automatically. You do not need to handle it in your handlers.

---

## 7. Middleware pipeline

### Execution order

Middleware added **first** runs **outermost** — it sees the request first and the response last.

```python
app.add_middleware(LoggingMiddleware())    # outermost: first pre, last post
app.add_middleware(CORSMiddleware())
app.add_middleware(RequestIDMiddleware()) # innermost: last pre, first post
```

Execution sequence:

```
→ LoggingMiddleware (pre)
  → CORSMiddleware (pre)
    → RequestIDMiddleware (pre)
      → route handler
    ← RequestIDMiddleware (post)
  ← CORSMiddleware (post)
← LoggingMiddleware (post)
```

### Writing custom middleware

See [Section 9](#9-writing-custom-middleware).

---

## 8. Error handling

### Automatic HTTP exception conversion

Any `HTTPException` (or subclass) raised anywhere in a handler is caught by `Application._route_handler` and converted to a JSON response:

```python
raise NotFoundException("User not found.")
# Response: 404 {"error": "User not found.", "status_code": 404}
```

### Unhandled exceptions

Any non-`HTTPException` raised in a handler is caught, logged with a full traceback via `logger.exception()`, and converted to a generic `500` response. The server never crashes due to a handler error.

```python
raise RuntimeError("database connection lost")
# Logs full traceback at ERROR level
# Response: 500 {"error": "Internal Server Error", "status_code": 500}
```

### Connection-level errors

`ConnectionHandler` separately catches:
- `asyncio.TimeoutError` — client took > 30 s to send headers → `408`
- `ValueError` from `RequestParser` — malformed request line → `400`
- Any other exception → `500`

---

## 9. Writing custom middleware

Subclass `BaseMiddleware` and implement `__call__`:

```python
from asyncweb import BaseMiddleware, Request, Response

class AuthMiddleware(BaseMiddleware):
    def __init__(self, secret: str) -> None:
        self._secret = secret

    async def __call__(self, request: Request, next_handler) -> Response:
        token = request.get_header("authorization")
        if token != f"Bearer {self._secret}":
            from asyncweb import ResponseFactory
            return ResponseFactory.error(401, "Unauthorized")
        return await next_handler(request)
```

Register it:

```python
app.add_middleware(AuthMiddleware(secret="my-secret-token"))
```

**Rules:**
- Always `await next_handler(request)` unless you intend to short-circuit (like the auth example above).
- Do not store per-request state on `self` — `__call__` runs concurrently for multiple connections.
- Place side-effect middleware (logging, metrics) before auth middleware so every request is recorded even if rejected.

---

## 10. Writing route handlers

Every handler is a plain `async def` function. No base class, no decorators other than the route registration.

```python
async def handler(request: Request) -> Response:
    ...
```

### Accessing request data

```python
req.method                     # "GET", "POST", etc.
req.path                       # "/users/42"
req.path_params["user_id"]     # "42"  (always a string)
req.query_params.get("q", "")  # query string value
req.get_header("content-type") # case-insensitive header lookup
req.json()                     # parse body as JSON → dict/list/etc.
req.text()                     # decode body as UTF-8 string
req.body                       # raw bytes
```

### Raising errors

```python
from asyncweb import BadRequestException, NotFoundException

raise BadRequestException("email is required")
raise NotFoundException(f"User {user_id} not found")
```

### Returning data

```python
from asyncweb import ResponseFactory

return ResponseFactory.json({"users": [...]})
return ResponseFactory.json(new_user, status_code=201)
return ResponseFactory.no_content()
return ResponseFactory.error(422, "Validation failed")
```

---

## 11. Configuration reference

### `Application.run()`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | Interface to bind. Use `"0.0.0.0"` to accept external connections. |
| `port` | `int` | `8000` | TCP port to listen on. |

### `CORSMiddleware`

| Parameter | Type | Default |
|---|---|---|
| `allow_origins` | `str` | `"*"` |
| `allow_methods` | `str` | `"GET, POST, PUT, PATCH, DELETE, OPTIONS"` |
| `allow_headers` | `str` | `"Content-Type, Authorization"` |

### `RequestParser` limits

| Constant | Value | Description |
|---|---|---|
| `_MAX_BODY_SIZE` | 10 MB | Maximum accepted request body size |

### `ConnectionHandler` limits

| Constant | Value | Description |
|---|---|---|
| `_READ_CHUNK` | 64 KB | Bytes read per `asyncio.StreamReader.read()` call |
| `_READ_TIMEOUT` | 30 s | Time allowed to receive the full request headers |

---

## 12. Testing guide

Tests live in `tests.py` and use only `unittest` from the stdlib.

### Running all tests

```bash
python tests.py
```

### Test classes

| Class | What it covers |
|---|---|
| `TestRequestParser` | Parsing GET, POST, query strings, headers, malformed input |
| `TestResponse` | JSON encoding, error bodies, `to_bytes()` wire format |
| `TestRouter` | Exact match, path params, method mismatch, decorators, introspection |
| `TestMiddleware` | CORS headers, preflight, request ID, logging passthrough, execution order |
| `TestApplication` | Full dispatch: 200, 404, 405, HTTP exceptions, unhandled exceptions, path params |

### Testing handlers in isolation

Because handlers are plain async functions, they are trivial to test without starting a server:

```python
import asyncio
from asyncweb import Request, ResponseFactory
import json

async def test_my_handler():
    req = Request(method="GET", path="/users/42", path_params={"user_id": "42"})
    response = await get_user(req)
    assert response.status_code == 200
    assert json.loads(response.body)["id"] == 42

asyncio.run(test_my_handler())
```

### Suppressing log output during tests

Add at the top of `tests.py`:

```python
import logging
logging.disable(logging.CRITICAL)
```

---

## 13. Platform notes

### Windows

`asyncio.loop.add_signal_handler()` is not available on Windows. AsyncWeb handles this automatically:

- `SIGTERM` is only registered on Unix/macOS.
- On Windows, the server uses a polling loop (`_serve_forever_windows`) that wakes every 0.5 s, allowing `KeyboardInterrupt` from Ctrl+C to propagate cleanly through `asyncio.run()`.

No code changes are needed — the same `asyncio.run(app.run())` call works on all platforms.

### Unix / macOS

Both `SIGINT` (Ctrl+C) and `SIGTERM` (e.g. `kill <pid>`, Docker stop) trigger a graceful shutdown.

---

## 14. Extension points

The framework is designed to be extended without modifying existing code (OCP).

| What to extend | How |
|---|---|
| New route | `@app.router.get("/path")` decorator or `app.router.add_route(...)` |
| New middleware | Subclass `BaseMiddleware`, implement `__call__`, call `app.add_middleware(...)` |
| New HTTP exception | Subclass `HTTPException`, set `status_code` and `default_detail` |
| New response type | Add a `@classmethod` to `ResponseFactory` |
| Custom body parsing | Add a method to `Request` or parse `req.body` directly in your handler |
| Custom path matching | Subclass `Router` and override `_compile()` |
| Multiple routers | Create separate `Router` instances and merge their routes into `app.router` |