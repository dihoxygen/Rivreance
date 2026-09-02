# Rivreance Agent Guide

This document orients AI agents working in the Rivreance repository. Read it before making changes.

## Project Overview

Rivreance is a full-stack learning project that maps USGS water conditions onto NHD river segments in a single watershed. The MVP delivers a **traffic-style river map**: river segments are color-coded by current water conditions, sourced from USGS continuous (sensor) and discrete (field measurement) data.

## MVP Scope

- **Target basins:** HUC-8 codes **03160112** (*Upper Black Warrior*) and **03160113** (*Lower Black Warrior*)
- **Geographic scope:** One watershed at a time; do not attempt national-scale ingestion
- **Primary coloring parameter:** Streamflow (`parameter_code=00060`) or gage height (`00065`)

## Stack

| Layer | Technology |
|-------|------------|
| Data pipeline | Python 3.12+ (httpx, GeoPandas, Shapely) |
| API | FastAPI |
| Frontend | Next.js + TypeScript + MapLibre GL JS |
| Database | Supabase (Postgres + PostGIS) |
| Scheduling | Python script + `pg_cron` or GitHub Actions |

## Data Sources

Use the **modern USGS OGC API** only:

- Base URL: `https://api.waterdata.usgs.gov/ogcapi/v0/`
- Key collections: `monitoring-locations`, `latest-continuous`, `field-measurements`, `time-series-metadata`
- River geometry: USGS National Hydrologic Geospatial Fabric `nhdflowline_network`

**Do not** use legacy WaterServices endpoints (retiring ~Q1 2027).

**Ingestion pattern:** Query `monitoring-locations` filtered by basin bbox or HUC, then use returned site IDs for continuous/discrete endpoints.

## Condition Classification

| Color | Meaning | MVP Rule |
|-------|---------|----------|
| Green | Normal | 25th–75th percentile (30-day) |
| Yellow | Elevated / below normal | 75th–90th or 10th–25th percentile |
| Red | Extreme | Above 90th, below 10th, or above flood stage |
| Gray | Unknown / stale | No reading or older than threshold |

## Planned Repository Layout

```
rivreance/
├── backend/
│   ├── etl/           # ingest_sites, ingest_observations, ingest_flowlines, compute_segment_conditions
│   ├── api/           # FastAPI: /health, /basin, /segments GeoJSON
│   └── lib/           # usgs_client.py, classify.py
├── frontend/          # Next.js App Router + MapLibre components
├── supabase/
│   └── migrations/    # PostGIS schema
├── .env.example
└── README.md
```

## Supabase Schema (MVP)

Enable PostGIS. Core tables:

- `basins` — HUC-8 id, name, bbox geometry
- `monitoring_sites` — USGS site id, name, point geom, flood stage metadata
- `observations` — unified continuous + discrete readings
- `river_segments` — NHD comid, LineString geom
- `segment_conditions` — segment status, color, source gage, computed_at
- `ingestion_runs` — pipeline audit log

**Security:** Public `SELECT` on read tables for MVP; writes only via service role from Python ETL. Enable RLS on all public tables.

## Implementation Phases

1. **Phase 0 — Discovery:** Prototype OGC API + Fabric flowline queries for the target HUC-8
2. **Phase 1 — Schema:** Supabase init, PostGIS migration, core tables
3. **Phase 2 — ETL:** Python pipeline for sites, observations, flowlines, segment conditions
4. **Phase 3 — API:** FastAPI GeoJSON endpoints
5. **Phase 4 — Map:** Next.js + MapLibre UI with colored segments, gage popups, legend
6. **Phase 5 — Deploy:** Schedule ETL cron, deploy frontend, document setup

See `.cursor/plans/rivreance_water_map_72809feb.plan.md` for full architecture and future phases (MCP tools, ML forecasting).

## Agent Working Guidelines

### Scope and conventions

- Minimize diff scope; match existing naming, types, and patterns
- Keep secrets server-side: `USGS_API_KEY` and Supabase service role key belong in backend/ETL only, never in the browser
- Scope all Fabric and OGC queries to the MVP basin bbox
- Prefer idempotent upserts and structured logging in ETL scripts

### Geospatial logic

- MVP colors segments **near** gages via spatial join (nearest segment within ~500 m), not full hydrologic routing
- Mark segments with no nearby gage or stale data (>2 h) as gray
- Cache flowlines locally; refresh weekly or on basin change

### When adding code

- **Python:** Owns data ingestion, classification, and API
- **TypeScript:** Owns map presentation and UI
- Document new env vars in `.env.example`
- Add GiST indexes on geometry columns; btree on `(site_id, observed_at DESC)`

### Testing and verification

- Verify ETL against a small bbox before full basin ingest
- Confirm map renders colored segments and gage popups for the target HUC-8
- Check that stale/unknown segments render gray with a visible "last updated" timestamp

## Success Criteria (MVP)

- [ ] ETL runs on schedule and populates Supabase without manual steps
- [ ] Map shows NHD river segments color-coded by condition in the target basin
- [ ] Gage popups show continuous and discrete readings where available
- [ ] Legend explains colors; "last updated" is visible
- [ ] Code is split cleanly: Python owns data, TypeScript owns presentation
- [ ] `.env.example` documents all required keys (no secrets committed)

## References

- [USGS Water Data OGC API](https://api.waterdata.usgs.gov/ogcapi/v0/)
- [USGS National Hydrologic Geospatial Fabric](https://api.water.usgs.gov/fabric/pygeoapi/collections/nhdflowline_network)
- [Watershed Boundary Dataset](https://www.usgs.gov/national-hydrography/watershed-boundary-dataset)
- Supabase plugin is enabled in `.cursor/settings.json` — use Supabase skills for database, auth, and migration work
