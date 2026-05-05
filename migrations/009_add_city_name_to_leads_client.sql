-- Проекция leads_client: city_name и owner_name из myhome_statement_json (не из leads.city_name).
-- После migrations/008_recreate_leads_client_v2.sql.

ALTER TABLE leads_client
    ADD COLUMN IF NOT EXISTS city_name TEXT;

ALTER TABLE leads_client
    ADD COLUMN IF NOT EXISTS owner_name TEXT;

COMMENT ON COLUMN leads_client.city_name IS 'statement.city_name (myhome_statement_json ->> ''city_name''); синхронизируется sync_leads_client_from_lead.';
COMMENT ON COLUMN leads_client.owner_name IS 'statement.owner_name (myhome_statement_json ->> ''owner_name''); синхронизируется sync_leads_client_from_lead.';

UPDATE leads_client lc
SET
    city_name = NULLIF(TRIM(l.myhome_statement_json ->> 'city_name'), ''),
    owner_name = NULLIF(TRIM(l.myhome_statement_json ->> 'owner_name'), '')
FROM leads l
WHERE lc.source = l.source
    AND lc.external_id = l.external_id;

CREATE OR REPLACE FUNCTION sync_leads_client_from_lead ()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
DECLARE
    j JSONB := NEW.myhome_statement_json;
    m_city_name TEXT;
    m_owner_name TEXT;
    m_district_name TEXT;
    m_dynamic_title TEXT;
    m_urban_name TEXT;
    m_images JSONB;
    m_bedrooms INTEGER;
    m_floor TEXT;
    m_total_floors INTEGER;
    parts TEXT[];
    fl_num INTEGER;
    tf_num INTEGER;
BEGIN
    m_city_name := NULLIF(TRIM(j ->> 'city_name'), '');
    m_owner_name := NULLIF(TRIM(j ->> 'owner_name'), '');
    m_district_name := COALESCE(
        NULLIF(TRIM(j ->> 'district_name'), ''),
        NULLIF(TRIM(NEW.district), ''));
    m_dynamic_title := NULLIF(TRIM(j ->> 'dynamic_title'), '');
    m_urban_name := NULLIF(TRIM(j ->> 'urban_name'), '');
    IF j IS NOT NULL AND (j ? 'images') AND jsonb_typeof(j -> 'images') = 'array' THEN
        m_images := j -> 'images';
    ELSE
        m_images := NULL;
    END IF;
    -- bedrooms: только из JSON (room); иначе NULL
    m_bedrooms := NULL;
    IF j IS NOT NULL AND (j ? 'room') THEN
        IF jsonb_typeof(j -> 'room') = 'number' THEN
            m_bedrooms := (j ->> 'room')::integer;
        ELSIF jsonb_typeof(j -> 'room') = 'string' AND (j ->> 'room') ~ '^[0-9]+$' THEN
            m_bedrooms := (j ->> 'room')::integer;
        END IF;
    END IF;
    m_floor := NULL;
    m_total_floors := NULL;
    IF j IS NOT NULL THEN
        fl_num := NULL;
        tf_num := NULL;
        IF jsonb_typeof(j -> 'floor') = 'number' THEN
            fl_num := (j ->> 'floor')::integer;
        ELSIF jsonb_typeof(j -> 'floor') = 'string' AND (j ->> 'floor') ~ '^[0-9]+$' THEN
            fl_num := (j ->> 'floor')::integer;
        END IF;
        IF jsonb_typeof(j -> 'total_floors') = 'number' THEN
            tf_num := (j ->> 'total_floors')::integer;
        ELSIF jsonb_typeof(j -> 'total_floors') = 'string' AND (j ->> 'total_floors') ~ '^[0-9]+$' THEN
            tf_num := (j ->> 'total_floors')::integer;
        END IF;
        IF fl_num IS NOT NULL AND tf_num IS NOT NULL THEN
            m_floor := fl_num::text || '/' || tf_num::text;
            m_total_floors := tf_num;
        ELSIF fl_num IS NOT NULL THEN
            m_floor := fl_num::text;
        ELSIF jsonb_typeof(j -> 'floor') = 'string' AND NULLIF(TRIM(j ->> 'floor'), '') IS NOT NULL THEN
            m_floor := TRIM(j ->> 'floor');
        END IF;
        IF m_total_floors IS NULL AND tf_num IS NOT NULL THEN
            m_total_floors := tf_num;
        END IF;
    END IF;
    IF m_floor IS NULL AND NEW.floor IS NOT NULL AND length(trim(NEW.floor)) > 0 THEN
        m_floor := trim(NEW.floor);
    END IF;
    IF m_total_floors IS NULL AND m_floor IS NOT NULL THEN
        parts := regexp_match(trim(m_floor), '^([0-9]+)/([0-9]+)(?:[^\d].*)?$');
        IF parts IS NOT NULL AND array_length(parts, 1) >= 2 THEN
            m_total_floors := parts[2]::integer;
        END IF;
    END IF;

    INSERT INTO leads_client (
        source,
        external_id,
        synced_at,
        status,
        score,
        phone,
        address,
        city_name,
        owner_name,
        district_name,
        area_m2,
        rooms,
        bedrooms,
        floor,
        total_floors,
        comment,
        is_owner,
        price_gel,
        price_usd,
        price_m2_usd,
        published_at,
        geo_lat,
        geo_lng,
        listing_views,
        pdf_url,
        dynamic_title,
        urban_name,
        images)
    VALUES (
        NEW.source,
        NEW.external_id,
        now(),
        NEW.status,
        NEW.score,
        NEW.phone,
        NEW.address,
        m_city_name,
        m_owner_name,
        m_district_name,
        NEW.area_m2,
        NEW.rooms,
        m_bedrooms,
        m_floor,
        m_total_floors,
        NEW.description,
        NEW.is_owner,
        NEW.price_gel,
        NEW.price_usd,
        NEW.price_m2_usd,
        NEW.published_at,
        NEW.geo_lat,
        NEW.geo_lng,
        NEW.listing_views,
        NEW.pdf_url,
        m_dynamic_title,
        m_urban_name,
        m_images)
ON CONFLICT (source, external_id)
    DO UPDATE SET
        synced_at = EXCLUDED.synced_at,
        status = EXCLUDED.status,
        score = EXCLUDED.score,
        phone = EXCLUDED.phone,
        address = EXCLUDED.address,
        city_name = EXCLUDED.city_name,
        owner_name = EXCLUDED.owner_name,
        district_name = EXCLUDED.district_name,
        area_m2 = EXCLUDED.area_m2,
        rooms = EXCLUDED.rooms,
        bedrooms = EXCLUDED.bedrooms,
        floor = EXCLUDED.floor,
        total_floors = EXCLUDED.total_floors,
        comment = EXCLUDED.comment,
        is_owner = EXCLUDED.is_owner,
        price_gel = EXCLUDED.price_gel,
        price_usd = EXCLUDED.price_usd,
        price_m2_usd = EXCLUDED.price_m2_usd,
        published_at = EXCLUDED.published_at,
        geo_lat = EXCLUDED.geo_lat,
        geo_lng = EXCLUDED.geo_lng,
        listing_views = EXCLUDED.listing_views,
        pdf_url = EXCLUDED.pdf_url,
        dynamic_title = EXCLUDED.dynamic_title,
        urban_name = EXCLUDED.urban_name,
        images = EXCLUDED.images;

    RETURN NEW;
END;
$$;
