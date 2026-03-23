-- Engram — PostgreSQL Schema

-- ── Users ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ── Memories ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content       TEXT NOT NULL,
    type          VARCHAR(50)  DEFAULT 'fact',
    source        VARCHAR(100) DEFAULT 'api',
    user_id       VARCHAR(100) DEFAULT 'default',
    tags          TEXT[]       DEFAULT '{}',
    confidence    FLOAT        DEFAULT 1.0,
    is_latest     BOOLEAN      DEFAULT TRUE,
    is_valid      BOOLEAN      DEFAULT TRUE,
    has_pii       BOOLEAN      DEFAULT FALSE,
    ttl_expires_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    invalid_at    TIMESTAMPTZ
);

-- ── PII Vault ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pii_vault (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token          VARCHAR(100) UNIQUE NOT NULL,
    original_value TEXT NOT NULL,
    pii_type       VARCHAR(50),
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ── Contradiction Flags ────────────────────────────────────
CREATE TABLE IF NOT EXISTS contradiction_flags (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    new_memory_id         TEXT,
    conflicting_memory_id TEXT,
    reason                TEXT,
    resolved              BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Audit Log ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id  TEXT,
    action     VARCHAR(50),
    reason     TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_memories_user    ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_valid   ON memories(is_latest, is_valid);
CREATE INDEX IF NOT EXISTS idx_memories_ttl     ON memories(ttl_expires_at);
CREATE INDEX IF NOT EXISTS idx_memories_type    ON memories(type);
CREATE INDEX IF NOT EXISTS idx_audit_memory_id  ON audit_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_action     ON audit_log(action);
