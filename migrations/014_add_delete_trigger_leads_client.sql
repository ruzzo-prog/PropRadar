-- Триггер каскадного удаления: при DELETE из leads → удаляется строка в leads_client.
-- До этого триггера DELETE в leads оставлял сироты в leads_client.
-- INSERT/UPDATE покрыт trg_leads_sync_client (migrations/008_recreate_leads_client_v2.sql).

CREATE OR REPLACE FUNCTION delete_leads_client_from_lead()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM leads_client
    WHERE source = OLD.source AND external_id = OLD.external_id;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE TRIGGER trg_leads_delete_client
    AFTER DELETE ON leads
    FOR EACH ROW EXECUTE FUNCTION delete_leads_client_from_lead();
