# AsyncWeb

A minimal, production-structured asynchronous JSON web server built **completely from scratch** in Python — no frameworks, no third-party dependencies, pure stdlib only (`asyncio`, `re`, `json`, `signal`).

Built to demonstrate clean architecture: SOLID principles, classic design patterns, and a codebase that is easy to read, extend, and test.

---

## Features

- Async TCP server via `asyncio` — handles many concurrent connections
- Decorator-based routing (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`)
- Path parameters — `/users/{user_id}`
- Query string parsing — `/search?q=hello&limit=10`
- JSON request body parsing and JSON response serialisation
- Middleware pipeline — logging, CORS, request ID (and easy to add your own)
- Structured HTTP exception hierarchy (400, 404, 405, 500, …)
- Graceful shutdown on Ctrl+C — cross-platform (Windows + Unix/macOS)
- 29 unit tests, zero external test dependencies

---

## Requirements

- Python 3.10 or higher
- No external packages — stdlib only

---

## Project structure

```
web server/
│   example_app.py       ← runnable demo (full CRUD API)
│   tests.py             ← 29 unit tests
│
└───asyncweb/
    │   __init__.py      ← public re-exports
    │
    ├───core/
    │       request.py   ← Request model + RequestParser
    │       response.py  ← Response model + ResponseFactory
    │       server.py    ← ConnectionHandler + Application
    │
    ├───routing/
    │       router.py    ← URL router with path-param support
    │
    ├───middleware/
    │       __init__.py  ← BaseMiddleware, built-ins, MiddlewarePipeline
    │
    └───exceptions/
            __init__.py  ← HTTPException hierarchy
```

---

## Quick start

### 1. Run the example app

```bash
python example_app.py
```

```
16:50:16  INFO  asyncweb.core.server — 🚀  AsyncWeb listening on http://127.0.0.1:8000
16:50:16  INFO  asyncweb.core.server — Press Ctrl+C to stop.
```

### 2. Test it with curl

```bash
# Health check
curl http://127.0.0.1:8000/health

# List users
curl http://127.0.0.1:8000/users

# Create a user
curl -X POST http://127.0.0.1:8000/users \
     -H "Content-Type: application/json" \
     -d "{\"name\": \"Alice\", \"email\": \"alice@example.com\"}"

# Get a user by ID
curl http://127.0.0.1:8000/users/1

# Update a user
curl -X PUT http://127.0.0.1:8000/users/1 \
     -H "Content-Type: application/json" \
     -d "{\"name\": \"Alice Updated\"}"

# Delete a user
curl -X DELETE http://127.0.0.1:8000/users/1

# List all registered routes
curl http://127.0.0.1:8000/routes
```

### 3. Run the tests

```bash
python tests.py
```

```
Ran 29 tests in 0.007s
OK
```

---

## Write your own app in 5 minutes

```python
import asyncio
import logging
from asyncweb import Application, ResponseFactory, LoggingMiddleware, CORSMiddleware

logging.basicConfig(level=logging.INFO)

app = Application()
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware())

@app.router.get("/hello")
async def hello(req):
    return ResponseFactory.json({"message": "Hello, world!"})

@app.router.get("/hello/{name}")
async def hello_name(req):
    name = req.path_params["name"]
    return ResponseFactory.json({"message": f"Hello, {name}!"})

@app.router.post("/echo")
async def echo(req):
    data = req.json()
    return ResponseFactory.json(data, status_code=201)

asyncio.run(app.run(host="127.0.0.1", port=8000))
```

---

## License

MIT