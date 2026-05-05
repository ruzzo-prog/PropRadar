-- API-first myhome.ge: геометка, просмотры, снимок ответа detail, PDF URL.
-- После migrations/004_add_text_lang_columns.sql.

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS geo_lat NUMERIC(12, 8),
    ADD COLUMN IF NOT EXISTS geo_lng NUMERIC(12, 8),
    ADD COLUMN IF NOT EXISTS listing_views INTEGER,
    ADD COLUMN IF NOT EXISTS myhome_statement_json JSONB,
    ADD COLUMN IF NOT EXISTS pdf_url TEXT;

COMMENT ON COLUMN leads.geo_lat IS 'Широта из API statement.lat (WGS84)';
COMMENT ON COLUMN leads.geo_lng IS 'Долгота из API statement.lng';
COMMENT ON COLUMN leads.listing_views IS 'views из detail statement';
COMMENT ON COLUMN leads.myhome_statement_json IS 'Полный объект statement из GET /v1/statements/{id}';
COMMENT ON COLUMN leads.pdf_url IS 'URL или публичный путь выгруженного PDF объявления';

DROP INDEX IF EXISTS idx_leads_myhome_pending_enrich;

CREATE INDEX IF NOT EXISTS idx_leads_myhome_pending_detail
    ON leads (source, created_at)
    WHERE source = 'myhome' AND status = 'new' AND address IS NULL;

CREATE INDEX IF NOT EXISTS idx_leads_myhome_pending_phone
    ON leads (source, created_at)
    WHERE source = 'myhome'
          AND status = 'new'
          AND (phone IS NULL OR phone = '');

CREATE INDEX IF NOT EXISTS idx_leads_myhome_pending_pdf
    ON leads (source, created_at)
    WHERE source = 'myhome'
          AND status = 'new'
          AND address IS NOT NULL
          AND address <> ''
          AND pdf_url IS NULL;
