-- Seed data for the Rivreance MVP.
--
-- `basins` is required before the ETL can upsert sites or segments. The threshold and
-- cross-section rows mirror backend/config/*.json (which stays the source of truth for
-- the pipeline); they are skipped until the matching gage has been ingested.

insert into public.basins (huc8, name, bbox, center, default_zoom)
values
    (
        '03160112',
        'Upper Black Warrior',
        st_makeenvelope(-87.7434, 33.1264, -86.7785, 33.8426, 4326),
        st_setsrid(st_makepoint(-87.2610, 33.4845), 4326),
        9.0
    ),
    (
        '03160113',
        'Lower Black Warrior',
        st_makeenvelope(-87.9426, 32.4100, -87.2401, 33.3260, 4326),
        st_setsrid(st_makepoint(-87.5914, 32.8680), 4326),
        9.0
    )
on conflict (huc8) do update
set name = excluded.name,
    bbox = excluded.bbox,
    center = excluded.center,
    default_zoom = excluded.default_zoom;

-- Provisional activity windows (cfs). Not safety ratings; tune with local knowledge.
insert into public.activity_thresholds
    (site_id, activity, min_cfs, opt_min_cfs, opt_max_cfs, max_cfs, source, note)
select *
from (
    values
        ('USGS-02465000', 'kayaking',  500.0, 1500.0, 12000.0, 30000.0),
        ('USGS-02465000', 'fishing',   300.0,  800.0,  8000.0, 20000.0),
        ('USGS-02466030', 'kayaking',  600.0, 1800.0, 14000.0, 35000.0),
        ('USGS-02466030', 'fishing',   400.0, 1000.0,  9000.0, 22000.0),
        ('USGS-02462000', 'kayaking',   60.0,  120.0,    800.0, 1500.0),
        ('USGS-02462000', 'fishing',    15.0,   40.0,    300.0,  800.0),
        ('USGS-02464000', 'kayaking',   40.0,   80.0,    600.0, 1200.0),
        ('USGS-02464000', 'fishing',     5.0,   15.0,    200.0,  600.0),
        ('USGS-02466500', 'kayaking',   25.0,   60.0,    500.0, 1000.0),
        ('USGS-02466500', 'fishing',     3.0,   10.0,    150.0,  500.0)
) as seed (site_id, activity, min_cfs, opt_min_cfs, opt_max_cfs, max_cfs)
cross join (values ('curated', 'Provisional window; tune with local knowledge')) as meta (source, note)
where exists (select 1 from public.monitoring_sites s where s.site_id = seed.site_id)
on conflict (site_id, activity) do update
set min_cfs = excluded.min_cfs,
    opt_min_cfs = excluded.opt_min_cfs,
    opt_max_cfs = excluded.opt_max_cfs,
    max_cfs = excluded.max_cfs,
    source = excluded.source,
    note = excluded.note;

-- Estimated trapezoidal channel geometry for the velocity engine's Q/A fallback.
insert into public.cross_sections
    (site_id, bottom_width_ft, side_slope, zero_flow_stage_ft, manning_n, channel_slope, source)
select *
from (
    values
        ('USGS-02462000', 100.0, 2.5, 2.5, 0.040, 0.0012,
         'estimated from USGS channel measurements (width 114-136 ft)'),
        ('USGS-02461500', 45.0, 2.0, 4.6, 0.038, 0.0015,
         'estimated from USGS channel measurements')
) as seed (site_id, bottom_width_ft, side_slope, zero_flow_stage_ft, manning_n, channel_slope, source)
where exists (select 1 from public.monitoring_sites s where s.site_id = seed.site_id)
on conflict (site_id) do update
set bottom_width_ft = excluded.bottom_width_ft,
    side_slope = excluded.side_slope,
    zero_flow_stage_ft = excluded.zero_flow_stage_ft,
    manning_n = excluded.manning_n,
    channel_slope = excluded.channel_slope,
    source = excluded.source;
