"""
Engram — Database Connection Factories

Single place for all DB connections. Supports both:
  - Local Docker (default): individual host/port settings
  - Hosted services: single URL env var

PostgreSQL:
  Local:  POSTGRES_HOST/PORT/DB/USER/PASSWORD (docker-compose defaults)
  Hosted: DATABASE_URL=postgresql://user:pass@host/db  (Neon, Supabase, Railway)

Qdrant:
  Local:  QDRANT_HOST/PORT (docker-compose default)
  Hosted: QDRANT_URL=https://xyz.cloud.qdrant.io  + QDRANT_API_KEY  (Qdrant Cloud)

Redis:
  Local:  REDIS_HOST/PORT (docker-compose default)
  Hosted: REDIS_URL=rediss://default:pass@host:port  (Upstash, Redis Cloud)

FalkorDB:
  Local only for now — no managed hosted option with a free tier.
  Keep running via docker-compose for graph features.

Usage in any backend module:
  from db import get_pg, get_qdrant, get_redis

  conn   = get_pg()        # psycopg2 connection
  client = get_qdrant()    # QdrantClient
  r      = get_redis()     # redis.Redis
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_root_env = Path(__file__).parent.parent / ".env"
_backend_env = Path(__file__).parent / ".env"
if _root_env.exists():
    load_dotenv(str(_root_env), override=False)
elif _backend_env.exists():
    load_dotenv(str(_backend_env), override=False)

import psycopg2
from qdrant_client import QdrantClient
import redis as redis_lib
from config import get_settings

settings = get_settings()


# ── PostgreSQL ────────────────────────────────────────────────────

def get_pg() -> psycopg2.extensions.connection:
    """
    Returns a psycopg2 connection.

    Priority:
      1. DATABASE_URL env var  (Neon / Supabase / Railway connection string)
      2. Individual POSTGRES_* settings (local Docker)

    Neon connection strings look like:
      postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/dbname?sslmode=require
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        # Neon requires sslmode=require — ensure it's present
        if "neon.tech" in database_url and "sslmode" not in database_url:
            sep = "&" if "?" in database_url else "?"
            database_url += f"{sep}sslmode=require"
        return psycopg2.connect(database_url)

    # Fall back to individual settings (local Docker)
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


# ── Qdrant ────────────────────────────────────────────────────────

def get_qdrant() -> QdrantClient:
    """
    Returns a QdrantClient.

    Priority:
      1. QDRANT_URL + QDRANT_API_KEY  (Qdrant Cloud)
      2. QDRANT_HOST / QDRANT_PORT    (local Docker)

    Qdrant Cloud URLs look like:
      https://xyz.us-east4-0.gcp.cloud.qdrant.io
    """
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()

    if qdrant_url:
        return QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)

    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


# ── Redis ─────────────────────────────────────────────────────────

def get_redis() -> redis_lib.Redis:
    """
    Returns a redis.Redis client.

    Priority:
      1. REDIS_URL env var   (Upstash / Redis Cloud)
      2. REDIS_HOST / PORT   (local Docker)

    Upstash URLs look like:
      rediss://default:pass@xyz.upstash.io:6379

    Note: Upstash uses TLS (rediss://) — the redis-py client handles this
    automatically when the URL scheme is rediss://.
    """
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        return redis_lib.from_url(redis_url, decode_responses=True)

    return redis_lib.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )
