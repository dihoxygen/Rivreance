-- Rivreance MVP schema: USGS gage observations mapped onto NHD river segments.
--
-- Column names match the Pydantic models in backend/lib/models.py so the ETL can
-- upsert straight through PostgREST. Reads are public; writes happen only with the
-- service-role key from the Python pipeline.

create extension if not exists postgis;

-- ---------------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------------

create table if not exists public.basins (
    huc8          text primary key,
    name          text not null,
    bbox          geometry(Polygon, 4326) not null,
    center        geometry(Point, 4326) not null,
    default_zoom  double precision not null default 9.0,
    created_at    timestamptz not null default now()
);

comment on table public.basins is 'HUC-8 watersheds in MVP scope.';

create table if not exists public.monitoring_sites (
    site_id                text primary key,
    site_number            text not null,
    name                   text not null,
    latitude               double precision not null,
    longitude              double precision not null,
    huc8                   text not null references public.basins (huc8) on delete cascade,
    huc12                  text,
    site_type              text,
    drainage_area_sqmi     double precision,
    flood_stage_ft         double precision,
    -- Populated by the flowline snap step in etl/ingest_sites.py.
    comid                  bigint,
    levelpath_id           double precision,
    path_length_km         double precision,
    segment_drainage_sqkm  double precision,
    snap_distance_m        double precision,
    updated_at             timestamptz not null default now(),
    geom                   geometry(Point, 4326)
        generated always as (st_setsrid(st_makepoint(longitude, latitude), 4326)) stored
);

create index if not exists monitoring_sites_geom_idx on public.monitoring_sites using gist (geom);
create index if not exists monitoring_sites_huc8_idx on public.monitoring_sites (huc8);

create table if not exists public.river_segments (
    comid              bigint primary key,
    huc8               text not null references public.basins (huc8) on delete cascade,
    name               text,
    reach_code         text,
    stream_order       integer,
    length_km          double precision,
    slope              double precision,
    levelpath_id       double precision,
    path_length_km     double precision,
    drainage_sqkm      double precision,
    erom_flow_cfs      double precision,
    erom_velocity_fps  double precision,
    geom               geometry(MultiLineString, 4326) not null,
    updated_at         timestamptz not null default now()
);

comment on column public.river_segments.levelpath_id is
    'NHDPlus level path: the mainstem a segment belongs to, used to propagate gage status.';

create index if not exists river_segments_geom_idx on public.river_segments using gist (geom);
create index if not exists river_segments_huc8_idx on public.river_segments (huc8);
create index if not exists river_segments_levelpath_idx on public.river_segments (levelpath_id);

-- Per-gage tuning: curated activity windows and channel geometry. Mirrors
-- backend/config/*.json so thresholds can eventually be edited without a deploy.
create table if not exists public.activity_thresholds (
    site_id         text not null references public.monitoring_sites (site_id) on delete cascade,
    activity        text not null check (activity in ('kayaking', 'fishing')),
    parameter_code  text not null default '00060',
    min_cfs         double precision not null,
    opt_min_cfs     double precision not null,
    opt_max_cfs     double precision not null,
    max_cfs         double precision not null,
    source          text not null default 'curated',
    note            text,
    primary key (site_id, activity),
    constraint activity_thresholds_ordered check (
        min_cfs <= opt_min_cfs and opt_min_cfs <= opt_max_cfs and opt_max_cfs <= max_cfs
    )
);

create table if not exists public.cross_sections (
    site_id             text primary key references public.monitoring_sites (site_id) on delete cascade,
    bottom_width_ft     double precision not null check (bottom_width_ft > 0),
    side_slope          double precision not null default 2.0,
    zero_flow_stage_ft  double precision not null default 0.0,
    manning_n           double precision not null default 0.035 check (manning_n > 0),
    channel_slope       double precision,
    source              text not null default 'configured'
);

-- ---------------------------------------------------------------------------
-- Observations
-- ---------------------------------------------------------------------------

create table if not exists public.observations (
    site_id          text not null references public.monitoring_sites (site_id) on delete cascade,
    parameter_code   text not null,
    value            double precision not null,
    unit             text not null default '',
    observed_at      timestamptz not null,
    source           text not null default 'continuous' check (source in ('continuous', 'field')),
    approval_status  text,
    qualifier        text,
    primary key (site_id, parameter_code, observed_at, source)
);

create index if not exists observations_site_time_idx
    on public.observations (site_id, observed_at desc);

-- Short instantaneous history for popup charts, kept as one row per time series.
create table if not exists public.site_series (
    site_id         text not null references public.monitoring_sites (site_id) on delete cascade,
    parameter_code  text not null,
    unit            text not null default '',
    points          jsonb not null default '[]'::jsonb,
    updated_at      timestamptz not null default now(),
    primary key (site_id, parameter_code)
);

create table if not exists public.parameter_stats (
    site_id         text not null references public.monitoring_sites (site_id) on delete cascade,
    parameter_code  text not null,
    window_days     integer not null,
    "count"         integer not null,
    source          text not null default 'daily' check (source in ('daily', 'continuous')),
    p05             double precision not null,
    p10             double precision not null,
    p25             double precision not null,
    p50             double precision not null,
    p75             double precision not null,
    p90             double precision not null,
    p95             double precision not null,
    updated_at      timestamptz not null default now(),
    primary key (site_id, parameter_code)
);

create table if not exists public.station_ratings (
    site_id            text primary key references public.monitoring_sites (site_id) on delete cascade,
    velocity_rating    jsonb,
    area_rating        jsonb,
    median_width_ft    double precision,
    measurement_count  integer not null default 0,
    fitted_at          timestamptz
);

comment on table public.station_ratings is
    'Power-law velocity/area ratings fitted from USGS discrete channel measurements.';

-- ---------------------------------------------------------------------------
-- Derived conditions
-- ---------------------------------------------------------------------------

create table if not exists public.site_conditions (
    site_id           text not null references public.monitoring_sites (site_id) on delete cascade,
    activity          text not null check (activity in ('kayaking', 'fishing')),
    status            text not null check (status in ('green', 'yellow', 'red', 'gray')),
    color             text not null,
    reason            text not null,
    metric_parameter  text,
    metric_value      double precision,
    unit              text,
    observed_at       timestamptz,
    age_minutes       double precision,
    discharge_cfs     double precision,
    gage_height_ft    double precision,
    percentile        double precision,
    thresholds        jsonb,
    velocity          jsonb,
    trend             text not null default 'unknown'
        check (trend in ('rising', 'falling', 'steady', 'unknown')),
    updated_at        timestamptz not null default now(),
    primary key (site_id, activity)
);

create table if not exists public.segment_conditions (
    comid           bigint not null references public.river_segments (comid) on delete cascade,
    huc8            text not null references public.basins (huc8) on delete cascade,
    activity        text not null check (activity in ('kayaking', 'fishing')),
    status          text not null check (status in ('green', 'yellow', 'red', 'gray')),
    color           text not null,
    source_site_id  text references public.monitoring_sites (site_id) on delete set null,
    assignment      text not null default 'unassigned'
        check (assignment in ('mainstem', 'proximity', 'unassigned')),
    distance_km     double precision,
    reason          text not null default 'no nearby gage',
    computed_at     timestamptz not null,
    primary key (comid, activity)
);

create index if not exists segment_conditions_basin_activity_idx
    on public.segment_conditions (huc8, activity);

create table if not exists public.ingestion_runs (
    run_id       text primary key,
    started_at   timestamptz not null,
    finished_at  timestamptz,
    status       text not null default 'running' check (status in ('running', 'success', 'failed')),
    basins       jsonb not null default '[]'::jsonb,
    counts       jsonb not null default '{}'::jsonb,
    error        text
);

create index if not exists ingestion_runs_started_idx on public.ingestion_runs (started_at desc);

-- ---------------------------------------------------------------------------
-- Read views and RPCs
-- ---------------------------------------------------------------------------

-- Geometry as GeoJSON coordinate arrays, so the Python store can read segments back
-- without parsing WKB.
create or replace view public.v_river_segments
with (security_invoker = true) as
select
    comid,
    huc8,
    name,
    reach_code,
    stream_order,
    length_km,
    slope,
    levelpath_id,
    path_length_km,
    drainage_sqkm,
    erom_flow_cfs,
    erom_velocity_fps,
    (st_asgeojson(geom)::jsonb -> 'coordinates') as geometry
from public.river_segments;

-- One-call GeoJSON FeatureCollection for the map: segments plus their condition.
create or replace function public.get_basin_segment_conditions(
    p_huc8 text,
    p_activity text default 'kayaking',
    p_min_stream_order integer default 1
)
returns jsonb
language sql
stable
security invoker
set search_path = public, extensions
as $$
    select jsonb_build_object(
        'type', 'FeatureCollection',
        'features', coalesce(jsonb_agg(feature), '[]'::jsonb)
    )
    from (
        select jsonb_build_object(
            'type', 'Feature',
            'id', s.comid,
            'geometry', st_asgeojson(s.geom)::jsonb,
            'properties', jsonb_build_object(
                'comid', s.comid,
                'name', s.name,
                'stream_order', s.stream_order,
                'length_km', s.length_km,
                'status', coalesce(c.status, 'gray'),
                'color', coalesce(c.color, '#9aa0a6'),
                'assignment', coalesce(c.assignment, 'unassigned'),
                'reason', coalesce(c.reason, 'no condition computed yet'),
                'source_site_id', c.source_site_id,
                'distance_km', c.distance_km,
                'computed_at', c.computed_at
            )
        ) as feature
        from public.river_segments s
        left join public.segment_conditions c
            on c.comid = s.comid and c.activity = p_activity
        where s.huc8 = p_huc8
          and coalesce(s.stream_order, 0) >= p_min_stream_order
    ) features;
$$;

-- Gages within a radius of a point — used by the planned MCP `find_sites_near` tool.
create or replace function public.find_sites_near(
    p_longitude double precision,
    p_latitude double precision,
    p_radius_km double precision default 25
)
returns table (
    site_id text,
    name text,
    distance_km double precision
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
    select
        s.site_id,
        s.name,
        st_distance(s.geom::geography, st_setsrid(st_makepoint(p_longitude, p_latitude), 4326)::geography)
            / 1000.0 as distance_km
    from public.monitoring_sites s
    where st_dwithin(
        s.geom::geography,
        st_setsrid(st_makepoint(p_longitude, p_latitude), 4326)::geography,
        p_radius_km * 1000.0
    )
    order by distance_km;
$$;

-- ---------------------------------------------------------------------------
-- Row level security: public read, service-role write
-- ---------------------------------------------------------------------------

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'basins',
        'monitoring_sites',
        'river_segments',
        'activity_thresholds',
        'cross_sections',
        'observations',
        'site_series',
        'parameter_stats',
        'station_ratings',
        'site_conditions',
        'segment_conditions',
        'ingestion_runs'
    ]
    loop
        execute format('alter table public.%I enable row level security', table_name);
        execute format('drop policy if exists %I on public.%I', table_name || '_public_read', table_name);
        execute format(
            'create policy %I on public.%I for select to anon, authenticated using (true)',
            table_name || '_public_read',
            table_name
        );
    end loop;
end
$$;
