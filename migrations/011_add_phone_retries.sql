-- Очередь телефона: счётчик попыток HTTP/2captcha (max 3 → status_reason phone_enrich_failed).

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS phone_retries INTEGER NOT NULL DEFAULT 0;

ALTER TABLE leads
    DROP CONSTRAINT IF EXISTS leads_phone_retries_range;

ALTER TABLE leads
    ADD CONSTRAINT leads_phone_retries_range CHECK (phone_retries >= 0 AND phone_retries <= 10);

CREATE INDEX IF NOT EXISTS idx_leads_myhome_phone_pending
    ON leads (source, status, created_at)
    WHERE source = 'myhome'
      AND status = 'new'
      AND (phone IS NULL OR phone = '')
      AND phone_retries < 3;
