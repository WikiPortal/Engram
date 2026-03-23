-- Engram — PostgreSQL Schema
-- Auto-runs on first docker compose up

-- ── Memories ──────────────────────────────────────────────
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

-- ── PII Vault ─────────────────────────────────────────────
-- Real PII values stored here, tokens used everywhere else
CREATE TABLE IF NOT EXISTS pii_vault (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token         VARCHAR(100) UNIQUE NOT NULL,
    original_value TEXT NOT NULL,
    pii_type      VARCHAR(50),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Contradiction Flags ───────────────────────────────────
-- When new memory conflicts with old one, logged here
CREATE TABLE IF NOT EXISTS contradiction_flags (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    new_memory_id         TEXT,
    conflicting_memory_id TEXT,
    reason                TEXT,
    resolved              BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Audit Log ─────────────────────────────────────────────
-- Full history of every memory action — never lose data
CREATE TABLE IF NOT EXISTS audit_log (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id  TEXT,
    action     VARCHAR(50),   -- CREATED | INVALIDATED | CONSOLIDATED | EXPIRED
    reason     TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_memories_user    ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_valid   ON memories(is_latest, is_valid);
CREATE INDEX IF NOT EXISTS idx_memories_ttl     ON memories(ttl_expires_at);
CREATE INDEX IF NOT EXISTS idx_memories_type    ON memories(type);
CREATE INDEX IF NOT EXISTS idx_audit_memory_id  ON audit_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_action     ON audit_log(action);
