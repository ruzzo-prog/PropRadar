-- Пересоздание проекции leads_client: PK (source, external_id), 26 клиентских столбцов, без lead_id / source_listing_uuid / языковых меток.
-- После migrations/007_create_leads_client_table.sql.

DROP TRIGGER IF EXISTS trg_leads_sync_client ON leads;

DROP FUNCTION IF EXISTS sync_leads_client_from_lead ();

DROP TABLE IF EXISTS leads_client;

CREATE TABLE leads_client (
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(256) NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(32) NOT NULL,
    score INTEGER NOT NULL,
    phone TEXT,
    address TEXT,
    district_name TEXT,
    area_m2 NUMERIC(12, 2),
    rooms INTEGER,
    bedrooms INTEGER,
    floor TEXT,
    total_floors INTEGER,
    comment TEXT,
    is_owner BOOLEAN NOT NULL,
    price_gel BIGINT,
    price_usd BIGINT,
    price_m2_usd BIGINT,
    published_at TIMESTAMPTZ,
    geo_lat NUMERIC(12, 8),
    geo_lng NUMERIC(12, 8),
    listing_views INTEGER,
    pdf_url TEXT,
    dynamic_title TEXT,
    urban_name TEXT,
    images JSONB,
    PRIMARY KEY (source, external_id),
    CONSTRAINT leads_client_score_range CHECK (score >= 0 AND score <= 100)
);

COMMENT ON TABLE leads_client IS 'Проекция leads + фрагмент statement API; синхронизируется триггером INSERT/UPDATE на leads. PK (source, external_id).';
COMMENT ON COLUMN leads_client.district_name IS 'COALESCE(TRIM(statement.district_name), TRIM(leads.district))';
COMMENT ON COLUMN leads_client.dynamic_title IS 'statement.dynamic_title';
COMMENT ON COLUMN leads_client.urban_name IS 'statement.urban_name';

COMMENT ON COLUMN leads_client.images IS 'statement.images — только если JSON-массив, иначе NULL';
COMMENT ON COLUMN leads_client.bedrooms IS 'Комнатность из JSON statement (room): только JSON, иначе NULL';
COMMENT ON COLUMN leads_client.floor IS 'Этаж: сначала JSON (floor/total_floors), иначе leads.floor / разбор X/Y';
COMMENT ON COLUMN leads_client.total_floors IS 'Этажность: сначала JSON total_floors, иначе второй компонент X/Y из floor';
COMMENT ON COLUMN leads_client.comment IS 'Текст из leads.description';
COMMENT ON COLUMN leads_client.rooms IS 'leads.rooms (данные ядра, в т.ч. без JSON)';

CREATE INDEX IF NOT EXISTS idx_leads_client_external_id ON leads_client (external_id);

CREATE INDEX IF NOT EXISTS idx_leads_client_district_name ON leads_client (district_name);

CREATE OR REPLACE FUNCTION sync_leads_client_from_lead ()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
DECLARE
    j JSONB := NEW.myhome_statement_json;
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

INSERT INTO leads_client (
    source,
    external_id,
    synced_at,
    status,
    score,
    phone,
    address,
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
SELECT
    s.source,
    s.external_id,
    now(),
    s.status,
    s.score,
    s.phone,
    s.address,
    s.district_name,
    s.area_m2,
    s.rooms,
    s.bedrooms,
    s.floor_display,
    COALESCE(
        s.total_floors_json,
        CASE WHEN regexp_match(trim(COALESCE(s.floor_display, '')), '^([0-9]+)/([0-9]+)(?:[^\d].*)?$') IS NOT NULL THEN
            (regexp_match(trim(s.floor_display), '^([0-9]+)/([0-9]+)(?:[^\d].*)?$'))[2]::integer
        ELSE
            NULL
        END),
    s.description,
    s.is_owner,
    s.price_gel,
    s.price_usd,
    s.price_m2_usd,
    s.published_at,
    s.geo_lat,
    s.geo_lng,
    s.listing_views,
    s.pdf_url,
    s.dynamic_title,
    s.urban_name,
    s.images
FROM (
    SELECT
        l.source,
        l.external_id,
        l.status,
        l.score,
        l.phone,
        l.address,
        COALESCE(
            NULLIF(TRIM(l.myhome_statement_json ->> 'district_name'), ''),
            NULLIF(TRIM(l.district), '')) AS district_name,
        l.area_m2,
        l.rooms,
        CASE WHEN l.myhome_statement_json IS NOT NULL
            AND (l.myhome_statement_json ? 'room')
            AND jsonb_typeof(l.myhome_statement_json -> 'room') = 'number' THEN
            (l.myhome_statement_json ->> 'room')::integer
        WHEN l.myhome_statement_json IS NOT NULL
            AND (l.myhome_statement_json ? 'room')
            AND jsonb_typeof(l.myhome_statement_json -> 'room') = 'string'
            AND (l.myhome_statement_json ->> 'room') ~ '^[0-9]+$' THEN
            (l.myhome_statement_json ->> 'room')::integer
        ELSE
            NULL
        END AS bedrooms,
        COALESCE(
            CASE WHEN l.myhome_statement_json IS NOT NULL
                AND jsonb_typeof(l.myhome_statement_json -> 'floor') = 'number'
                AND jsonb_typeof(l.myhome_statement_json -> 'total_floors') = 'number' THEN
                (l.myhome_statement_json ->> 'floor') || '/' || (l.myhome_statement_json ->> 'total_floors')
            WHEN l.myhome_statement_json IS NOT NULL
                AND jsonb_typeof(l.myhome_statement_json -> 'floor') = 'number' THEN
                (l.myhome_statement_json ->> 'floor')
            WHEN l.myhome_statement_json IS NOT NULL
                AND jsonb_typeof(l.myhome_statement_json -> 'floor') = 'string'
                AND NULLIF(TRIM(l.myhome_statement_json ->> 'floor'), '') IS NOT NULL THEN
                TRIM(l.myhome_statement_json ->> 'floor')
            ELSE
                NULL
            END,
            NULLIF(TRIM(l.floor), '')) AS floor_display,
        CASE WHEN l.myhome_statement_json IS NOT NULL
            AND jsonb_typeof(l.myhome_statement_json -> 'total_floors') = 'number' THEN
            (l.myhome_statement_json ->> 'total_floors')::integer
        WHEN l.myhome_statement_json IS NOT NULL
            AND jsonb_typeof(l.myhome_statement_json -> 'total_floors') = 'string'
            AND (l.myhome_statement_json ->> 'total_floors') ~ '^[0-9]+$' THEN
            (l.myhome_statement_json ->> 'total_floors')::integer
        ELSE
            NULL
        END AS total_floors_json,
        l.description,
        l.is_owner,
        l.price_gel,
        l.price_usd,
        l.price_m2_usd,
        l.published_at,
        l.geo_lat,
        l.geo_lng,
        l.listing_views,
        l.pdf_url,
        NULLIF(TRIM(l.myhome_statement_json ->> 'dynamic_title'), '') AS dynamic_title,
        NULLIF(TRIM(l.myhome_statement_json ->> 'urban_name'), '') AS urban_name,
        CASE WHEN l.myhome_statement_json IS NOT NULL
            AND (l.myhome_statement_json ? 'images')
            AND jsonb_typeof(l.myhome_statement_json -> 'images') = 'array' THEN
            l.myhome_statement_json -> 'images'
        ELSE
            NULL
        END AS images
    FROM
        leads l) AS s
ON CONFLICT (source, external_id)
    DO UPDATE SET
        synced_at = EXCLUDED.synced_at,
        status = EXCLUDED.status,
        score = EXCLUDED.score,
        phone = EXCLUDED.phone,
        address = EXCLUDED.address,
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

CREATE TRIGGER trg_leads_sync_client
    AFTER INSERT OR UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION sync_leads_client_from_lead ();
