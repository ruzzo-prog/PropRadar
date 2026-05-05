-- Myhome: явная колонка GEL, переименование price_total_usd → price_usd.
-- После migrations/005_myhome_api_first.sql.

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS price_gel BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'leads'
          AND column_name = 'price_total_usd'
    ) THEN
        ALTER TABLE leads RENAME COLUMN price_total_usd TO price_usd;
    END IF;
END $$;

COMMENT ON COLUMN leads.price_gel IS 'Итого в GEL из API price.1';
COMMENT ON COLUMN leads.price_usd IS 'Итого в USD из API price.2 (ранее price_total_usd)';
