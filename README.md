# Rivreance

A traffic-style river map: NHD river segments colored **green / yellow / red** by live
USGS water conditions, with estimated channel velocity, so a kayaker or angler can tell
at a glance whether a reach is worth the drive.

```
USGS OGC APIs → Python ETL → store (JSON snapshot or Supabase/PostGIS) → FastAPI → Next.js + MapLibre
```

The MVP is scoped to two HUC-8 watersheds: **03160112** (Upper Black Warrior) and
**03160113** (Lower Black Warrior).

---

## What it does

- **Colored river segments.** NHDPlus v2 flowlines from the USGS geospatial Fabric are
  colored from the nearest relevant gage: green inside the optimal flow window, yellow
  when runnable but low or pushy, red when too low or too high, gray when unknown.
- **Activity toggle.** Kayaking and fishing use different flow windows, so the whole map
  re-colors when you switch. Curated windows live in
  `backend/config/activity_thresholds.json`; stations without one fall back to
  percentiles of their own recent record, shifted per activity.
- **Velocity estimates.** USGS gages publish discharge and stage, not velocity, so
  Rivreance estimates it and always says how (see below).
- **Honest gray.** Readings older than two hours, stage-only lock-and-dam gages, and
  reaches with no nearby gage stay gray rather than guessing.
- **24-hour trend charts** in each gage popup, so you can see rising versus falling water.

---

## Velocity estimation

Methods are tried in order of trustworthiness and the chosen one is reported in the UI:

| Method | Formula | When it is used |
| --- | --- | --- |
| Field velocity rating | `v = k·Q^m` fitted from the station's own USGS `channel-measurements` | Whenever ≥ 4 measurements fit with R² ≥ 0.5 and Q is near the measured range |
| Field area rating | `A = k·Q^m`, then `v = Q/A` | Station measures area but not velocity |
| Trapezoidal cross-section | `A = W·d + m·d²`, then `v = Q/A` | Channel geometry configured in `backend/config/cross_sections.json` |
| Manning's equation | `v = (1.486/n)·R^(2/3)·S^(1/2)` | Stage is available but discharge is not |
| NHDPlus EROM | `v ≈ v_ma·(Q/Q_ma)^0.4` | Last resort, from reach mean-annual values |

Most Black Warrior gages land on the first method: they have decades of field visits, so
the rating is fitted from real measurements rather than assumed geometry. Velocities are
reported in both mph and ft/s, with a confidence level and the fit's R².

---

## Repository layout

```
backend/
  lib/          usgs.py (OGC clients) · velocity.py · rating.py · classify.py
                conditions.py (gage → segment propagation) · geo.py · store.py · cache.py
  etl/          ingest_flowlines · ingest_sites · ingest_observations
                compute_conditions · run_pipeline
  api/          FastAPI GeoJSON endpoints
  config/       basins.json · activity_thresholds.json · cross_sections.json
  tests/        108 tests (hydraulics, ratings, classification, spatial join, API)
frontend/
  app/          Next.js App Router shell and map page
  components/   RiverMap · SitePopup · TrendChart · Legend · ActivityToggle · StatusBanner
  lib/          typed API client, formatting, MapLibre style
supabase/
  migrations/   PostGIS schema, RLS policies, GeoJSON view and RPCs
  seed.sql      basins plus provisional thresholds and cross-sections
```

---

## Quickstart

Requires Python 3.12+ and Node 20+.

```bash
# 1. Backend dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"

# 2. Configuration (optional: a USGS API key raises rate limits)
cp .env.example .env

# 3. First pipeline run — --with-flowlines downloads river geometry (~40 s per basin)
cd backend
PYTHONPATH=. python -m etl.run_pipeline --with-flowlines

# 4. API on http://localhost:8000
PYTHONPATH=. uvicorn api.main:app --reload

# 5. Map on http://localhost:3000 (in another shell)
cd ../frontend
cp .env.local.example .env.local
npm install && npm run dev
```

Afterwards, refresh conditions every 15–30 minutes with the much faster:

```bash
cd backend && PYTHONPATH=. python -m etl.run_pipeline
```

### Checks

```bash
cd backend && python -m pytest && python -m ruff check .
cd frontend && npm run typecheck && npm run build
```

---

## API

Base path `/api/v1`. Responses are cached for `RIVREANCE_CACHE_TTL_SECONDS` (default 15
minutes) so browsers never translate into USGS requests.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Last ingestion run, its age, and whether data is stale |
| `GET /basins` | Basins in scope with bounding boxes |
| `GET /basins/{huc8}/segments?activity=&min_order=` | Colored river segments as GeoJSON |
| `GET /basins/{huc8}/sites?activity=` | Gage points with readings, condition, and velocity |
| `GET /sites/{site_id}/series?parameter=00060` | Cached 24-hour series for popup charts |

---

## Data sources

Only the modern USGS OGC APIs are used; the legacy WaterServices endpoints (retiring
around Q1 2027) are deliberately avoided.

- [USGS Water Data OGC API](https://api.waterdata.usgs.gov/ogcapi/v0/) —
  `monitoring-locations`, `latest-continuous`, `continuous`, `daily`,
  `channel-measurements`
- [USGS National Hydrologic Geospatial Fabric](https://api.water.usgs.gov/fabric/pygeoapi) —
  `nhdflowline_network` for river geometry, `wbd08_20250107` for basin boundaries
- [USGS National Map](https://basemap.nationalmap.gov/) — public-domain topo basemap tiles

Two quirks worth knowing, both handled in `lib/usgs.py`:

- `latest-continuous` also returns the final value of long-retired time series, so gages
  are filtered by reading age, not by presence.
- The Water Data API rejects `offset` whenever `sortby` is set, so sorted queries fetch a
  single large page instead of paging.

---

## Storage

`RIVREANCE_STORE_BACKEND` selects where pipeline output lands:

- `file` (default) — JSON snapshots in `backend/.data`, so the prototype runs with no
  cloud credentials.
- `supabase` — upserts through PostgREST with the service-role key. Apply
  `supabase/migrations/0001_init_rivreance.sql` and `supabase/seed.sql` first. Read
  policies are public; writes require the service role.

---

## Known limitations

- **No hydrologic routing.** A gage's status is propagated along its NHDPlus level path
  (bounded by along-path distance and a drainage-area sanity check), then by proximity
  within 5 km. Reaches between gages on different mainstems stay gray. NLDI-based routing
  is the intended next step.
- **Thresholds are provisional.** The curated windows are inferred from flow records, not
  from local safety guidance. Treat colors as a planning hint, never as a go/no-go call.
- **Velocity is a mean, not a hazard model.** A reach with a 2 mph mean can still hold
  dangerous features.
- **Stage-only gages cannot be classified.** Lock-and-dam pool gages report gage height
  with no discharge, so they render gray.

---

## Background: the hydrologic unit (HU)

- The hydrologic unit (HU) is a hierarchical system for standardizing the way data is
  collected, organized, mapped, and managed in the U.S. Watershed Boundary Dataset (WBD).
- It follows a nested pattern where each progressive hydrological unit is represented by
  an additional two-digit code for a successively smaller areal unit.
- The smaller the number, the larger the area; the larger the number, the smaller the
  area. For example, starting with the largest area 18 and progressing to 1846852186, the
  smallest region: 18 → 1846 → 184685 → 18468521 → 1846852186.

### HUC-8

- The WBD contains eight nested levels of progressive hydrological units (2–16 digit
  codes).
- HUC-12 coverage is complete for the United States.
- USGS continues its survey for Mexico and Canada.

### MVP HUC locations

To demonstrate project viability, this MVP targets specific hydrologic unit codes (HUC);
the future state will focus on broader zones. The MVP covers HUC codes **03160112**
(*Upper Black Warrior*) and **03160113** (*Lower Black Warrior*).
