"""
example_app.py — demonstrates every feature of AsyncWeb.

Run:
    python example_app.py

Then test with:
    curl http://localhost:8000/health
    curl http://localhost:8000/users
    curl -X POST http://localhost:8000/users \
         -H "Content-Type: application/json" \
         -d '{"name": "Alice", "email": "alice@example.com"}'
    curl http://localhost:8000/users/1
    curl -X PUT http://localhost:8000/users/1 \
         -H "Content-Type: application/json" \
         -d '{"name": "Alice Updated"}'
    curl -X DELETE http://localhost:8000/users/1
    curl http://localhost:8000/routes
"""

from asyncweb import (
    Application,
    BadRequestException,
    CORSMiddleware,
    LoggingMiddleware,
    NotFoundException,
    Request,
    RequestIDMiddleware,
    ResponseFactory,
)
import asyncio
import logging
import sys
import os

# Make the package importable when run from this directory
sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# In-memory "database"  (replace with a real DB adapter in production)
# ---------------------------------------------------------------------------
_users: dict[int, dict] = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob",   "email": "bob@example.com"},
}
_next_id = 3

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = Application()
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware())
app.add_middleware(RequestIDMiddleware())


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@app.router.get("/health")
async def health_check(req: Request):
    return ResponseFactory.json({"status": "ok"})


@app.router.get("/routes")
async def list_routes(req: Request):
    """Introspection endpoint — lists all registered routes."""
    return ResponseFactory.json(app.router.registered_routes())


# ── Users collection ──────────────────────────────────────────────────────

@app.router.get("/users")
async def list_users(req: Request):
    return ResponseFactory.json(list(_users.values()))


@app.router.post("/users")
async def create_user(req: Request):
    global _next_id
    try:
        data = req.json()
    except (ValueError, KeyError):
        raise BadRequestException("Request body must be valid JSON.")

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()

    if not name or not email:
        raise BadRequestException("Both 'name' and 'email' are required.")

    user = {"id": _next_id, "name": name, "email": email}
    _users[_next_id] = user
    _next_id += 1

    return ResponseFactory.json(user, status_code=201)


# ── Single user resource ──────────────────────────────────────────────────

@app.router.get("/users/{user_id}")
async def get_user(req: Request):
    user = _resolve_user(req)
    return ResponseFactory.json(user)


@app.router.put("/users/{user_id}")
async def update_user(req: Request):
    user = _resolve_user(req)
    try:
        data = req.json()
    except ValueError:
        raise BadRequestException("Request body must be valid JSON.")

    user.update({k: v for k, v in data.items() if k != "id"})
    return ResponseFactory.json(user)


@app.router.delete("/users/{user_id}")
async def delete_user(req: Request):
    user = _resolve_user(req)
    del _users[user["id"]]
    return ResponseFactory.no_content()


# ── Helper (avoids repetition across user handlers) ───────────────────────

def _resolve_user(req: Request) -> dict:
    """Extract and validate user_id from path params; raise 404 if missing."""
    try:
        user_id = int(req.path_params["user_id"])
    except (KeyError, ValueError):
        raise BadRequestException("user_id must be an integer.")

    user = _users.get(user_id)
    if user is None:
        raise NotFoundException(f"User {user_id} not found.")
    return user


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(app.run(host="127.0.0.1", port=8000))
