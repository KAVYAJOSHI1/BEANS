"""Login / logout and user management (ADMIN)."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from beans.api import auth, db

router = APIRouter(tags=["Users & Login"])


@router.post("/auth/login")
def login(payload: Dict[str, Any], response: Response):
    with db.connection() as conn:
        if not auth.auth_enabled(conn):
            raise HTTPException(409, "no users configured: BEANS runs in single-user mode")
        token = auth.login(conn, str(payload.get("username") or ""), str(payload.get("password") or ""))
    if not token:
        db.audit("LOGIN_FAILED", "USER", str(payload.get("username")), investigator="-")
        raise HTTPException(401, "wrong username or password")
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", max_age=int(auth.settings.SESSION_HOURS * 3600))
    db.audit("LOGIN", "USER", payload["username"], investigator=payload["username"])
    with db.connection() as conn:
        return {"user": auth.user_for_token(conn, token)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = auth.token_from(request)
    if token:
        with db.connection() as conn:
            auth.logout(conn, token)
    response.delete_cookie(auth.COOKIE)
    return {"status": "success"}


@router.get("/auth/me")
def me(request: Request):
    with db.connection() as conn:
        enabled = auth.auth_enabled(conn)
        user = auth.user_for_token(conn, auth.token_from(request)) if enabled else auth.SINGLE_USER
    return {"auth_enabled": enabled, "user": user, "roles": auth.ROLES}


@router.post("/auth/password")
def change_password(payload: Dict[str, Any]):
    user = auth.current_user()
    if not user["auth"]:
        raise HTTPException(409, "single-user mode has no passwords")
    with db.connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", [user["username"]]).fetchone()
        if not auth.verify_password(str(payload.get("current") or ""), row[0]):
            raise HTTPException(403, "current password is wrong")
        new = str(payload.get("new") or "")
        if len(new) < 10:
            raise HTTPException(422, "password must be at least 10 characters")
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", [auth.hash_password(new), user["username"]])
    db.audit("PASSWORD_CHANGE", "USER", user["username"])
    return {"status": "success"}


@router.get("/users", dependencies=[Depends(auth.require("ADMIN"))])
def list_users():
    return db.query("SELECT username, display_name, role, active, created_at FROM users ORDER BY created_at")


@router.post("/users", dependencies=[Depends(auth.require("ADMIN"))])
def add_user(payload: Dict[str, Any]):
    try:
        with db.connection() as conn:
            auth.create_user(conn, str(payload.get("username") or "").strip(), str(payload.get("password") or ""),
                             str(payload.get("role") or "ANALYST"), str(payload.get("display_name") or ""))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.audit("USER_ADD", "USER", payload["username"], {"role": payload.get("role")})
    return {"status": "success", "username": payload["username"]}


@router.patch("/users/{username}", dependencies=[Depends(auth.require("ADMIN"))])
def update_user(username: str, payload: Dict[str, Any]):
    if not db.scalar("SELECT COUNT(*) FROM users WHERE username = ?", [username]):
        raise HTTPException(404, f"user {username} not found")
    if username == auth.current_user()["username"] and (payload.get("active") is False or payload.get("role")):
        raise HTTPException(409, "you cannot deactivate yourself or change your own role")
    if "active" in payload:
        db.execute("UPDATE users SET active = ? WHERE username = ?", [bool(payload["active"]), username])
        if not payload["active"]:
            db.execute("DELETE FROM sessions WHERE username = ?", [username])
    if payload.get("role"):
        role = str(payload["role"]).upper()
        if role not in auth.ROLES:
            raise HTTPException(422, f"role must be one of {auth.ROLES}")
        db.execute("UPDATE users SET role = ? WHERE username = ?", [role, username])
    db.audit("USER_UPDATE", "USER", username, payload)
    return {"status": "success"}
