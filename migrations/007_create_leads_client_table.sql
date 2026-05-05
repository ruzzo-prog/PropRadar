-- Денормализованная проекция leads для клиентских выборок (Metabase/UI).
-- После migrations/006_add_price_gel_rename_price_usd.sql.
-- Инвариант: PK = lead_id (1:1 с leads); бизнес-ключ дублируется как UNIQUE (source, external_id).

CREATE TABLE IF NOT EXISTS leads_client (
    lead_id UUID PRIMARY KEY
        REFERENCES leads (id) ON DELETE CASCADE,
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(256) NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 25 полезных полей: ядро из leads + выдержка из myhome_statement_json (детерминированно).
    status VARCHAR(32) NOT NULL,
    score INTEGER NOT NULL,
    phone TEXT,
    address TEXT,
    address_lang VARCHAR(8),
    district_name TEXT,
    district_lang VARCHAR(8),
    area_m2 NUMERIC(12, 2),
    rooms INTEGER,
    floor TEXT,
    description TEXT,
    description_lang VARCHAR(8),
    is_owner BOOLEAN NOT NULL,
    price_gel BIGINT,
    price_usd BIGINT,
    price_m2_usd BIGINT,
    published_at TIMESTAMPTZ,
    geo_lat NUMERIC(12, 8),
    geo_lng NUMERIC(12, 8),
    listing_views INTEGER,
    pdf_url TEXT,
    source_listing_uuid UUID,
    dynamic_title TEXT,
    urban_name TEXT,
    images JSONB,

    CONSTRAINT leads_client_source_external_unique UNIQUE (source, external_id),
    CONSTRAINT leads_client_score_range CHECK (score >= 0 AND score <= 100)
);

COMMENT ON TABLE leads_client IS 'Проекция leads + фрагмент statement API; синхронизируется триггером INSERT/UPDATE на leads.';
COMMENT ON COLUMN leads_client.district_name IS 'COALESCE(TRIM(statement.district_name), TRIM(leads.district))';
COMMENT ON COLUMN leads_client.dynamic_title IS 'statement.dynamic_title';
COMMENT ON COLUMN leads_client.urban_name IS 'statement.urban_name';
COMMENT ON COLUMN leads_client.images IS 'statement.images — только если JSON-массив, иначе NULL';

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

    INSERT INTO leads_client (
        lead_id,
        source,
        external_id,
        synced_at,
        status,
        score,
        phone,
        address,
        address_lang,
        district_name,
        district_lang,
        area_m2,
        rooms,
        floor,
        description,
        description_lang,
        is_owner,
        price_gel,
        price_usd,
        price_m2_usd,
        published_at,
        geo_lat,
        geo_lng,
        listing_views,
        pdf_url,
        source_listing_uuid,
        dynamic_title,
        urban_name,
        images)
    VALUES (
        NEW.id,
        NEW.source,
        NEW.external_id,
        now(),
        NEW.status,
        NEW.score,
        NEW.phone,
        NEW.address,
        NEW.address_lang,
        m_district_name,
        NEW.district_lang,
        NEW.area_m2,
        NEW.rooms,
        NEW.floor,
        NEW.description,
        NEW.description_lang,
        NEW.is_owner,
        NEW.price_gel,
        NEW.price_usd,
        NEW.price_m2_usd,
        NEW.published_at,
        NEW.geo_lat,
        NEW.geo_lng,
        NEW.listing_views,
        NEW.pdf_url,
        NEW.source_listing_uuid,
        m_dynamic_title,
        m_urban_name,
        m_images)
ON CONFLICT (lead_id)
    DO UPDATE SET
        source = EXCLUDED.source,
        external_id = EXCLUDED.external_id,
        synced_at = EXCLUDED.synced_at,
        status = EXCLUDED.status,
        score = EXCLUDED.score,
        phone = EXCLUDED.phone,
        address = EXCLUDED.address,
        address_lang = EXCLUDED.address_lang,
        district_name = EXCLUDED.district_name,
        district_lang = EXCLUDED.district_lang,
        area_m2 = EXCLUDED.area_m2,
        rooms = EXCLUDED.rooms,
        floor = EXCLUDED.floor,
        description = EXCLUDED.description,
        description_lang = EXCLUDED.description_lang,
        is_owner = EXCLUDED.is_owner,
        price_gel = EXCLUDED.price_gel,
        price_usd = EXCLUDED.price_usd,
        price_m2_usd = EXCLUDED.price_m2_usd,
        published_at = EXCLUDED.published_at,
        geo_lat = EXCLUDED.geo_lat,
        geo_lng = EXCLUDED.geo_lng,
        listing_views = EXCLUDED.listing_views,
        pdf_url = EXCLUDED.pdf_url,
        source_listing_uuid = EXCLUDED.source_listing_uuid,
        dynamic_title = EXCLUDED.dynamic_title,
        urban_name = EXCLUDED.urban_name,
        images = EXCLUDED.images;

    RETURN NEW;
END;
$$;

-- Первичное заполнение до включения триггера (прямой upsert из leads).
INSERT INTO leads_client (
    lead_id,
    source,
    external_id,
    synced_at,
    status,
    score,
    phone,
    address,
    address_lang,
    district_name,
    district_lang,
    area_m2,
    rooms,
    floor,
    description,
    description_lang,
    is_owner,
    price_gel,
    price_usd,
    price_m2_usd,
    published_at,
    geo_lat,
    geo_lng,
    listing_views,
    pdf_url,
    source_listing_uuid,
    dynamic_title,
    urban_name,
    images)
SELECT
    l.id,
    l.source,
    l.external_id,
    now(),
    l.status,
    l.score,
    l.phone,
    l.address,
    l.address_lang,
    COALESCE(
        NULLIF(TRIM(l.myhome_statement_json ->> 'district_name'), ''),
        NULLIF(TRIM(l.district), '')),
    l.district_lang,
    l.area_m2,
    l.rooms,
    l.floor,
    l.description,
    l.description_lang,
    l.is_owner,
    l.price_gel,
    l.price_usd,
    l.price_m2_usd,
    l.published_at,
    l.geo_lat,
    l.geo_lng,
    l.listing_views,
    l.pdf_url,
    l.source_listing_uuid,
    NULLIF(TRIM(l.myhome_statement_json ->> 'dynamic_title'), ''),
    NULLIF(TRIM(l.myhome_statement_json ->> 'urban_name'), ''),
    CASE WHEN l.myhome_statement_json IS NOT NULL
        AND (l.myhome_statement_json ? 'images')
        AND jsonb_typeof(l.myhome_statement_json -> 'images') = 'array' THEN
        l.myhome_statement_json -> 'images'
    ELSE
        NULL
    END
FROM
    leads l
ON CONFLICT (lead_id)
    DO UPDATE SET
    source = EXCLUDED.source,
    external_id = EXCLUDED.external_id,
    synced_at = EXCLUDED.synced_at,
    status = EXCLUDED.status,
    score = EXCLUDED.score,
    phone = EXCLUDED.phone,
    address = EXCLUDED.address,
    address_lang = EXCLUDED.address_lang,
    district_name = EXCLUDED.district_name,
    district_lang = EXCLUDED.district_lang,
    area_m2 = EXCLUDED.area_m2,
    rooms = EXCLUDED.rooms,
    floor = EXCLUDED.floor,
    description = EXCLUDED.description,
    description_lang = EXCLUDED.description_lang,
    is_owner = EXCLUDED.is_owner,
    price_gel = EXCLUDED.price_gel,
    price_usd = EXCLUDED.price_usd,
    price_m2_usd = EXCLUDED.price_m2_usd,
    published_at = EXCLUDED.published_at,
    geo_lat = EXCLUDED.geo_lat,
    geo_lng = EXCLUDED.geo_lng,
    listing_views = EXCLUDED.listing_views,
    pdf_url = EXCLUDED.pdf_url,
    source_listing_uuid = EXCLUDED.source_listing_uuid,
    dynamic_title = EXCLUDED.dynamic_title,
    urban_name = EXCLUDED.urban_name,
    images = EXCLUDED.images;

DROP TRIGGER IF EXISTS trg_leads_sync_client ON leads;

CREATE TRIGGER trg_leads_sync_client
    AFTER INSERT OR UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION sync_leads_client_from_lead ();
