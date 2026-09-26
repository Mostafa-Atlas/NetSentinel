import hashlib
import hmac
import os
import secrets
import time
from datetime import UTC, timedelta
from typing import Annotated, NoReturn

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from netsentinel.models import Session as LoginSession
from netsentinel.models import User, utcnow

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
password_hasher = PasswordHasher()
SESSION_SECONDS = 12 * 60 * 60


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def error(code: str, message: str, status: int = 400) -> NoReturn:
    from fastapi import HTTPException

    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


Db = Annotated[DBSession, Depends(get_db)]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit

        if urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
            error("origin_denied", "Request origin does not match this server", 403)


def current_session(request: Request, db: Db) -> LoginSession:
    token = request.cookies.get("netsentinel_session")
    if not token:
        error("unauthorized", "Sign in required", 401)
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
    if login is None or login.expires_at.replace(tzinfo=UTC) <= utcnow():
        error("unauthorized", "Session expired or invalid", 401)
    return login


CurrentSession = Annotated[LoginSession, Depends(current_session)]


def require_csrf(request: Request, login: CurrentSession) -> None:
    same_origin(request)
    cookie = request.cookies.get("netsentinel_csrf", "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        error("csrf_denied", "CSRF token required", 403)
    if not hmac.compare_digest(digest(header), login.csrf_hash):
        error("csrf_denied", "CSRF token invalid", 403)


Csrf = Annotated[None, Depends(require_csrf)]


def set_session(response: Response, db: DBSession, user: User) -> None:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=utcnow() + timedelta(seconds=SESSION_SECONDS),
        )
    )
    db.commit()
    secure = os.getenv("NETSENTINEL_SECURE_COOKIES", "false").lower() == "true"
    response.set_cookie(
        "netsentinel_session",
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=SESSION_SECONDS,
    )
    response.set_cookie(
        "netsentinel_csrf",
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=SESSION_SECONDS,
    )


@router.get("/bootstrap-status")
def bootstrap_status(db: Db) -> dict[str, bool]:
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/bootstrap", status_code=201)
def bootstrap(payload: Credentials, request: Request, response: Response, db: Db) -> dict[str, str]:
    same_origin(request)
    if db.scalar(select(func.count(User.id))):
        error("already_initialized", "Administrator already exists", 409)
    user = User(username=payload.username, password_hash=password_hasher.hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        error("already_initialized", "Administrator already exists", 409)
    db.refresh(user)
    set_session(response, db, user)
    return {"username": user.username}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response, db: Db) -> dict[str, str]:
    same_origin(request)
    key = f"{request.client.host if request.client else 'unknown'}:{payload.username.lower()}"
    now = time.monotonic()
    attempts = [t for t in request.app.state.login_attempts.get(key, []) if now - t < 300]
    if len(attempts) >= 5:
        error("rate_limited", "Too many login attempts; retry later", 429)
    user = db.scalar(select(User).where(User.username == payload.username))
    try:
        valid = user is not None and password_hasher.verify(user.password_hash, payload.password)
    except VerificationError:
        valid = False
    if not valid or user is None:
        request.app.state.login_attempts[key] = [*attempts, now]
        error("invalid_credentials", "Invalid username or password", 401)
    request.app.state.login_attempts.pop(key, None)
    user.last_login_at = utcnow()
    db.commit()
    set_session(response, db, user)
    return {"username": user.username}


@router.post("/logout")
def logout(response: Response, login: CurrentSession, db: Db, _csrf: Csrf) -> dict[str, str]:
    db.delete(login)
    db.commit()
    response.delete_cookie("netsentinel_session")
    response.delete_cookie("netsentinel_csrf")
    return {"status": "signed_out"}


@router.get("/me")
def me(login: CurrentSession) -> dict[str, str]:
    return {"username": login.user.username}
