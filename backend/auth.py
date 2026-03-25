"""
Engram — Auth Module

Endpoints:
  POST /auth/register  — create account
  POST /auth/login     — returns access token (15 min) + refresh token (30 days)
  POST /auth/refresh   — exchange refresh token for a new access token
  POST /auth/logout    — revoke a refresh token
  GET  /auth/me        — get current user from access token

"""

import os
import uuid
import hashlib
import hmac
import base64
import json
import time
import secrets
from db import get_pg
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

_limiter = Limiter(key_func=get_remote_address)

# ── Token TTLs ────────────────────────────────────────────────────
ACCESS_TOKEN_TTL  = 60 * 15          
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 30  

SECRET = os.getenv("AUTH_SECRET", "engram-change-this-secret-in-production")


# ── JWT helpers ───────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body   = _b64url(json.dumps(payload).encode())
    sig    = _b64url(
        hmac.new(SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


def _verify(token: str) -> dict:
    try:
        header, body, sig = token.split(".")
        expected = _b64url(
            hmac.new(SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        pad = 4 - len(body) % 4
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * pad))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def _create_access_token(user_id: str, email: str, username: str) -> str:
    return _sign({
        "sub":      user_id,
        "email":    email,
        "username": username,
        "type":     "access",
        "iat":      int(time.time()),
        "exp":      int(time.time()) + ACCESS_TOKEN_TTL,
    })


# ── Refresh token helpers (Postgres-backed) ───────────────────────

def _create_refresh_token(user_id: str) -> str:
    """
    Generate a cryptographically random opaque refresh token,
    store its hash in Postgres, and return the raw token to the caller.
    We store the hash (not the raw token) so a DB breach can't be used
    to issue new access tokens.
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_TTL)

    conn = _pg()
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
           VALUES (%s, %s, %s, %s)""",
        (str(uuid.uuid4()), user_id, token_hash, expires_at)
    )
    conn.commit()
    cur.close(); conn.close()

    return raw_token


def _validate_refresh_token(raw_token: str) -> dict:
    """
    Validate a refresh token. Returns the associated user row.
    Raises 401 if token is invalid, expired, or revoked.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    conn = _pg()
    cur  = conn.cursor()
    cur.execute(
        """SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked,
                  u.email, u.username
           FROM refresh_tokens rt
           JOIN users u ON u.id = rt.user_id
           WHERE rt.token_hash = %s""",
        (token_hash,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        raise HTTPException(401, "Invalid refresh token")

    rt_id, user_id, expires_at, revoked, email, username = row

    if revoked:
        raise HTTPException(401, "Refresh token has been revoked")

    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(401, "Refresh token has expired. Please log in again.")

    return {
        "rt_id":    rt_id,
        "user_id":  user_id,
        "email":    email,
        "username": username,
    }


def _revoke_refresh_token(raw_token: str) -> bool:
    """Mark a refresh token as revoked. Returns True if found."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = _pg()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = %s",
        (token_hash,)
    )
    affected = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    return affected > 0


# ── Password hashing ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + key).decode()


def verify_password(password: str, stored: str) -> bool:
    raw  = base64.b64decode(stored.encode())
    salt = raw[:16]
    key  = raw[16:]
    return hmac.compare_digest(
        key,
        hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    )


# ── DB helper ─────────────────────────────────────────────────────

def _pg():
    return get_pg()


# ── FastAPI dependencies ──────────────────────────────────────────

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Sign in at /auth/login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify(creds.credentials)


def get_optional_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict | None:
    if not creds:
        return None
    try:
        return _verify(creds.credentials)
    except Exception:
        return None


# ── Request / Response models ─────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    str = Field(..., description="Email address")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email:    str
    password: str


class AuthResponse(BaseModel):
    access_token:  str
    refresh_token: str
    user_id:       str
    email:         str
    username:      str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id:  str
    email:    str
    username: str


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=201)
@_limiter.limit("5/hour")
def register(req: RegisterRequest, request: Request):
    """Create a new account. Returns access + refresh tokens."""
    if "@" not in req.email or "." not in req.email.split("@")[-1]:
        raise HTTPException(400, "Invalid email address")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)
    email   = req.email.lower().strip()
    uname   = req.username.strip()

    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (id, email, username, password_hash) VALUES (%s, %s, %s, %s)",
            (user_id, email, uname, pw_hash)
        )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, "Email or username already taken")
        raise HTTPException(500, f"Registration failed: {e}")

    access_token  = _create_access_token(user_id, email, uname)
    refresh_token = _create_refresh_token(user_id)

    return AuthResponse(
        access_token=access_token, refresh_token=refresh_token,
        user_id=user_id, email=email, username=uname,
    )


@router.post("/login", response_model=AuthResponse)
@_limiter.limit("10/minute")
def login(req: LoginRequest, request: Request):
    """Sign in. Returns a short-lived access token and a long-lived refresh token."""
    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, email, username, password_hash FROM users WHERE email = %s",
            (req.email.lower().strip(),)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(500, f"Login failed: {e}")

    if not row:
        raise HTTPException(401, "Invalid email or password")

    user_id, email, username, pw_hash = row

    if not verify_password(req.password, pw_hash):
        raise HTTPException(401, "Invalid email or password")

    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
        conn.commit()
        cur.close(); conn.close()
    except Exception:
        pass

    access_token  = _create_access_token(str(user_id), email, username)
    refresh_token = _create_refresh_token(str(user_id))

    return AuthResponse(
        access_token=access_token, refresh_token=refresh_token,
        user_id=str(user_id), email=email, username=username,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
@_limiter.limit("30/minute")
def refresh(req: RefreshRequest, request: Request):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token itself is NOT rotated — it stays valid until
    it expires or is explicitly revoked via /auth/logout.
    """
    user_info    = _validate_refresh_token(req.refresh_token)
    access_token = _create_access_token(
        user_info["user_id"],
        user_info["email"],
        user_info["username"],
    )
    return AccessTokenResponse(access_token=access_token)


@router.post("/logout", status_code=200)
def logout(req: LogoutRequest):
    """
    Revoke a refresh token. The user's access token will expire naturally
    within 15 minutes. For immediate invalidation on sensitive actions,
    the client should discard the access token locally.
    """
    found = _revoke_refresh_token(req.refresh_token)
    if not found:
        raise HTTPException(404, "Refresh token not found")
    return {"status": "logged out"}


@router.get("/me", response_model=MeResponse)
def me(current_user: dict = Depends(get_current_user)):
    """Return current user info from access token."""
    return MeResponse(
        user_id=current_user["sub"],
        email=current_user["email"],
        username=current_user["username"],
    )
