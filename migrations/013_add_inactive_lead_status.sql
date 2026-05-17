-- Статус inactive: объявление снято с myhome API (сверка со снапшотом), запись не удаляется.
-- После migrations/012_backfill_rooms_from_room_type_id.sql.

COMMENT ON COLUMN leads.status IS
    'new | inactive | contacted | qualified | rejected | converted; '
    'inactive = исчезло из API (ids-snapshot sync)';

CREATE INDEX IF NOT EXISTS idx_leads_myhome_status_new
    ON leads (source, external_id)
    WHERE status = 'new';
