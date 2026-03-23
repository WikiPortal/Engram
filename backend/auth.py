"""
Engram — Auth Module

Endpoints:
  POST /auth/register  — create account
  POST /auth/login     — get JWT token
  GET  /auth/me        — get current user from token

JWT is signed with AUTH_SECRET (set in .env).
All /memory/* and /chat endpoints require Authorization: Bearer <token>.
The token subject (sub) becomes the user_id for all memory operations.
"""

import os
import uuid
import hashlib
import hmac
import base64
import json
import time
from db import get_pg
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

# ── JWT (no external library needed) ─────────────────────────────

SECRET = os.getenv("AUTH_SECRET", "engram-change-this-secret-in-production")
TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days


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
        # Pad base64
        pad = 4 - len(body) % 4
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * pad))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def create_token(user_id: str, email: str, username: str) -> str:
    return _sign({
        "sub":      user_id,
        "email":    email,
        "username": username,
        "iat":      int(time.time()),
        "exp":      int(time.time()) + TOKEN_TTL,
    })


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


# ── DB helpers ────────────────────────────────────────────────────

def _pg():
    return get_pg()


# ── Dependency: get current user from JWT ─────────────────────────

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """
    FastAPI dependency. Validates JWT and returns payload.
    Use as: current_user: dict = Depends(get_current_user)
    Then use current_user["sub"] as the user_id.
    """
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Sign in at /auth/login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify(creds.credentials)


def get_optional_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict | None:
    """
    Like get_current_user but returns None instead of raising if no token.
    Used for endpoints that fall back to 'default' user when unauthenticated.
    """
    if not creds:
        return None
    try:
        return _verify(creds.credentials)
    except Exception:
        return None


# ── Request / Response models ─────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., description="Email address")
    username: str = Field(..., min_length=3, max_length=50, description="Display name")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str
    username: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    username: str


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=201)
def register(req: RegisterRequest):
    """Create a new account. Returns JWT token immediately."""
    # Basic email validation
    if "@" not in req.email or "." not in req.email.split("@")[-1]:
        raise HTTPException(400, "Invalid email address")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)

    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (id, email, username, password_hash) VALUES (%s, %s, %s, %s)",
            (user_id, req.email.lower().strip(), req.username.strip(), pw_hash)
        )
        conn.commit()
        cur.close(); conn.close()
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(409, "Email or username already taken")
    except Exception as e:
        raise HTTPException(500, f"Registration failed: {e}")

    token = create_token(user_id, req.email.lower().strip(), req.username.strip())
    return AuthResponse(token=token, user_id=user_id,
                        email=req.email.lower().strip(), username=req.username.strip())


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Sign in with email + password. Returns JWT token."""
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

    # Update last_login
    try:
        conn = _pg()
        cur  = conn.cursor()
        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
        conn.commit()
        cur.close(); conn.close()
    except Exception:
        pass  # non-critical

    token = create_token(str(user_id), email, username)
    return AuthResponse(token=token, user_id=str(user_id), email=email, username=username)


@router.get("/me", response_model=MeResponse)
def me(current_user: dict = Depends(get_current_user)):
    """Return current user info from JWT."""
    return MeResponse(
        user_id=current_user["sub"],
        email=current_user["email"],
        username=current_user["username"],
    )
