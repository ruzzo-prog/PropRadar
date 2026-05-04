-- Детали объявления и телефон (myhome enricher). Применять после 002_add_myhome_listing_fields.sql.

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS phone TEXT,
    ADD COLUMN IF NOT EXISTS address TEXT,
    ADD COLUMN IF NOT EXISTS district TEXT,
    ADD COLUMN IF NOT EXISTS area_m2 NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS rooms INTEGER,
    ADD COLUMN IF NOT EXISTS floor TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS is_owner BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_leads_myhome_pending_enrich
    ON leads (source, created_at)
    WHERE source = 'myhome' AND phone IS NULL AND status = 'new';
