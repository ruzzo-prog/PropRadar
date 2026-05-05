-- Языковые метки для текстовых полей myhome enricher (после 003_add_lead_details.sql).

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS address_lang VARCHAR(8),
    ADD COLUMN IF NOT EXISTS district_lang VARCHAR(8),
    ADD COLUMN IF NOT EXISTS description_lang VARCHAR(8);
