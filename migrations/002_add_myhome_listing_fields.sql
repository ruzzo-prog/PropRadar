-- Поля объявления myhome.ge (дополнение к leads).
-- Применять после 001_init_leads.sql.

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS source_listing_uuid UUID,
    ADD COLUMN IF NOT EXISTS price_total_usd BIGINT,
    ADD COLUMN IF NOT EXISTS price_m2_usd BIGINT,
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

COMMENT ON COLUMN leads.source_listing_uuid IS 'UUID объявления на myhome (для будущего запроса телефона)';
