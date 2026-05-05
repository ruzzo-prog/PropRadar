-- Причина смены статуса (machine-readable), например disappeared_from_api.
-- После migrations/009_add_city_name_to_leads_client.sql.

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS status_reason VARCHAR (128);

COMMENT ON COLUMN leads.status_reason IS 'Код причины статуса (например disappeared_from_api); не путать с текстом description.';
