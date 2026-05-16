-- Backfill leads.rooms from myhome_statement_json.room_type_id where ingest/detail had no "room".
-- Run once after deploy of resolve_rooms(); leads_client trigger fires on UPDATE.

UPDATE leads
SET rooms = (myhome_statement_json->>'room_type_id')::int
WHERE source = 'myhome'
  AND rooms IS NULL
  AND myhome_statement_json->>'room_type_id' ~ '^\d+$'
  AND (myhome_statement_json->>'room_type_id')::int > 0;
