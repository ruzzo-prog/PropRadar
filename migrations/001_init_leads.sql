-- Минимальная схема leads-db (PostgreSQL 15). Применять на чистую БД.
-- Инвариант: только leads-db, порт 5433 на хосте (см. docker/infra).

CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    score INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT leads_score_range CHECK (score >= 0 AND score <= 100),
    CONSTRAINT leads_source_external_unique UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads (score);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads (created_at);
