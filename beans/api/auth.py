"""Local users, roles and sessions (offline; no external identity provider).

Roles, lowest to highest: VIEWER (read only) < ANALYST (triage, cases, drafts) < SUPERVISOR (approves legal drafts,
configures webhooks and attribution) < ADMIN (manages users).

Authentication switches on as soon as one user exists (create the first one with `beans user add NAME --role admin`).
With no users, BEANS runs in open single-user mode exactly as before, so the offline demo needs no login and there is
never a default password. Passwords are salted PBKDF2-SHA256; sessions are random tokens in an HttpOnly cookie.
"""
import contextvars
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from beans.config import settings

ROLES = ["VIEWER", "ANALYST", "SUPERVISOR", "ADMIN"]
COOKIE = "beans_session"
PUBLIC = {"/api/health", "/api/auth/login", "/api/auth/me", "/api/config"}
PBKDF2_ITERATIONS = 310_000
MAX_FAILURES, LOCK_SECONDS = 5, 300
SINGLE_USER = {"username": "local", "display_name": "Single-user mode", "role": "ADMIN", "auth": False}

_current = contextvars.ContextVar("beans_user", default=None)
_failures: dict = {}
_fail_lock = threading.Lock()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return algo == "pbkdf2_sha256" and hmac.compare_digest(dk.hex(), digest)
    except (ValueError, AttributeError):
        return False


def auth_enabled(conn) -> bool:
    return bool(conn.execute("SELECT COUNT(*) FROM users WHERE active").fetchone()[0])


def create_user(conn, username: str, password: str, role: str, display_name: str = "") -> None:
    role = role.upper()
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    if not username or not username.replace("_", "").replace(".", "").isalnum():
        raise ValueError("username: letters, digits, '.' and '_' only")
    if conn.execute("SELECT COUNT(*) FROM users WHERE username = ?", [username]).fetchone()[0]:
        raise ValueError(f"user {username} already exists")
    conn.execute("INSERT INTO users (username, display_name, role, password_hash) VALUES (?, ?, ?, ?)",
                 [username, display_name or username, role, hash_password(password)])


def _locked(username: str) -> bool:
    with _fail_lock:
        n, since = _failures.get(username, (0, 0.0))
        if n >= MAX_FAILURES and time.time() - since < LOCK_SECONDS:
            return True
        if n >= MAX_FAILURES:
            _failures.pop(username, None)
        return False


def login(conn, username: str, password: str) -> Optional[str]:
    """Returns a session token, or None (wrong credentials / locked out)."""
    if _locked(username):
        raise HTTPException(429, f"too many failed attempts; try again in {LOCK_SECONDS // 60} minutes")
    row = conn.execute("SELECT password_hash FROM users WHERE username = ? AND active", [username]).fetchone()
    if not row or not verify_password(password, row[0]):
        with _fail_lock:
            n, _ = _failures.get(username, (0, 0.0))
            _failures[username] = (n + 1, time.time())
        return None
    with _fail_lock:
        _failures.pop(username, None)
    token = secrets.token_hex(32)
    conn.execute("INSERT INTO sessions (token_hash, username, expires_at) VALUES (?, ?, ?)",
                 [hashlib.sha256(token.encode()).hexdigest(), username,
                  datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.SESSION_HOURS)])
    return token


def logout(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", [hashlib.sha256(token.encode()).hexdigest()])


def user_for_token(conn, token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    row = conn.execute("""SELECT u.username, u.display_name, u.role FROM sessions s JOIN users u USING (username)
                          WHERE s.token_hash = ? AND s.expires_at > ? AND u.active""",
                       [hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc).replace(tzinfo=None)]).fetchone()
    return {"username": row[0], "display_name": row[1], "role": row[2], "auth": True} if row else None


def token_from(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else request.cookies.get(COOKIE)


def current_user() -> dict:
    return _current.get() or SINGLE_USER


def has_role(user: dict, role: str) -> bool:
    return ROLES.index(user["role"]) >= ROLES.index(role)


def require(role: str):
    """FastAPI dependency: the current user needs at least `role` (always true in single-user mode)."""
    def dep():
        user = current_user()
        if not has_role(user, role):
            raise HTTPException(403, f"requires the {role} role (you are {user['role']})")
        return user
    return dep


async def middleware(request: Request, call_next):
    """Every /api call needs a session once users exist; any change needs at least ANALYST."""
    path = request.url.path
    if not path.startswith(settings.API_PREFIX) or path in PUBLIC:
        return await call_next(request)
    from beans.api import db
    with db.connection() as conn:
        enabled = auth_enabled(conn)
        user = user_for_token(conn, token_from(request)) if enabled else None
    if enabled and user is None:
        return JSONResponse({"detail": "login required"}, status_code=401)
    if user and request.method not in ("GET", "HEAD", "OPTIONS") and not has_role(user, "ANALYST"):
        return JSONResponse({"detail": "read-only account (VIEWER)"}, status_code=403)
    tok = _current.set(user)
    try:
        return await call_next(request)
    finally:
        _current.reset(tok)
