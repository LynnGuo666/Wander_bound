"""Invite-only accounts and opaque bearer sessions for the private Spark app."""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

current_user: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_user", default=None)
ITERATIONS = 600_000
SESSION_SECONDS = 30 * 24 * 60 * 60
USERNAME = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class AccountStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("ACCOUNT_DB_PATH") or "data/accounts.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, role TEXT NOT NULL,
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS invites (
                    code_hash TEXT PRIMARY KEY, creator_id TEXT NOT NULL, used_by TEXT, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
            """)
        os.chmod(self.path, 0o600)

    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def register(self, username: str, password: str, invite: str) -> dict:
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise ValueError("用户名须为 3–32 位小写字母、数字、下划线或连字符，且以字母开头")
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ValueError("密码须为 12–128 个字符")
        if not isinstance(invite, str) or not invite:
            raise ValueError("邀请码无效")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            if first:
                bootstrap = os.getenv("BOOTSTRAP_INVITE_CODE", "")
                if not bootstrap or not hmac.compare_digest(invite, bootstrap):
                    raise ValueError("初始邀请码无效")
            else:
                row = db.execute("SELECT used_by FROM invites WHERE code_hash=?", (_digest(invite),)).fetchone()
                if not row or row["used_by"] is not None:
                    raise ValueError("邀请码无效或已使用")
            user_id = str(uuid.uuid4())
            salt = secrets.token_bytes(16)
            password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
            try:
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                           (user_id, username, "admin" if first else "member", salt, password_hash, int(time.time())))
            except sqlite3.IntegrityError as exc:
                raise ValueError("用户名已被使用") from exc
            if not first:
                db.execute("UPDATE invites SET used_by=? WHERE code_hash=?", (user_id, _digest(invite)))
        return {"id": user_id, "username": username, "role": "admin" if first else "member"}

    def login(self, username: str, password: str) -> tuple[dict, str]:
        if (not isinstance(username, str) or not USERNAME.fullmatch(username)
                or not isinstance(password, str) or len(password) > 128):
            raise ValueError("用户名或密码错误")
        with self.db() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                raise ValueError("用户名或密码错误")
            expected = hashlib.pbkdf2_hmac("sha256", password.encode(), row["salt"], ITERATIONS)
            if not hmac.compare_digest(expected, row["password_hash"]):
                raise ValueError("用户名或密码错误")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (_digest(token), row["id"], int(time.time()) + SESSION_SECONDS))
            return {"id": row["id"], "username": row["username"], "role": row["role"]}, token

    def authenticate(self, token: str) -> dict | None:
        if not token:
            return None
        with self.db() as db:
            row = db.execute("SELECT users.id, users.username, users.role FROM sessions JOIN users "
                             "ON users.id=sessions.user_id WHERE token_hash=? AND expires_at>?",
                             (_digest(token), int(time.time()))).fetchone()
            return dict(row) if row else None

    def logout(self, token: str) -> None:
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (_digest(token),))

    def create_invite(self, creator_id: str) -> str:
        code = secrets.token_urlsafe(24)
        with self.db() as db:
            db.execute("INSERT INTO invites VALUES (?, ?, NULL, ?)", (_digest(code), creator_id, int(time.time())))
        return code


def require_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None and not hasattr(request.state, "user"):
        bearer = request.headers.get("Authorization", "")
        token = bearer[7:] if bearer.startswith("Bearer ") else ""
        user = AccountStore().authenticate(token) if token else None
        request.state.user = user
    if not user:
        raise HTTPException(401, "请先登录")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user


def router_for(store: AccountStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/auth/register")
    async def register(payload: dict):
        try:
            user = store.register(payload.get("username"), payload.get("password"), payload.get("invite"))
            _, token = store.login(payload["username"], payload["password"])
            return {"user": user, "token": token}
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/api/auth/login")
    async def login(payload: dict):
        try:
            user, token = store.login(payload.get("username"), payload.get("password"))
            return {"user": user, "token": token}
        except (ValueError, TypeError):
            raise HTTPException(401, "用户名或密码错误") from None

    @router.get("/api/auth/me")
    async def me(request: Request):
        return {"user": require_user(request)}

    @router.post("/api/auth/logout")
    async def logout(request: Request):
        require_user(request)
        store.logout(request.headers.get("Authorization", "").removeprefix("Bearer "))
        return {"ok": True}

    @router.post("/api/auth/invites")
    async def invite(request: Request):
        user = require_admin(request)
        return {"invite": store.create_invite(user["id"])}

    return router
