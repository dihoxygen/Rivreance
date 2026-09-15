import type { Feature, FeatureCollection, MultiLineString, Point } from "geojson";

export type Status = "green" | "yellow" | "red" | "gray";
export type Activity = "kayaking" | "fishing";
export type Trend = "rising" | "falling" | "steady" | "unknown";
export type Assignment = "mainstem" | "proximity" | "unassigned";
export type VelocityConfidence = "high" | "medium" | "low";

export interface Basin {
  huc8: string;
  name: string;
  /** [west, south, east, north] */
  bbox: [number, number, number, number];
  /** [longitude, latitude] */
  center: [number, number];
  default_zoom: number;
}

export interface ActivityThresholds {
  activity: Activity;
  parameter_code: string;
  min_cfs: number;
  opt_min_cfs: number;
  opt_max_cfs: number;
  max_cfs: number;
  source: string;
  note: string | null;
}

export interface SegmentProperties {
  comid: number;
  name: string | null;
  stream_order: number | null;
  length_km: number | null;
  line_width: number;
  status: Status;
  color: string;
  assignment: Assignment;
  reason: string;
  source_site_id: string | null;
  distance_km: number | null;
  computed_at?: string;
}

export interface PowerLawRating {
  k: number;
  exponent: number;
  count: number;
  r_squared: number;
  q_min: number;
  q_max: number;
}

export interface StationRating {
  site_id: string;
  velocity_rating: PowerLawRating | null;
  area_rating: PowerLawRating | null;
  median_width_ft: number | null;
  measurement_count: number;
  fitted_at: string | null;
}

export interface SiteProperties {
  site_id: string;
  site_number: string;
  name: string;
  huc8: string;
  drainage_area_sqmi: number | null;
  comid: number | null;
  snap_distance_m: number | null;
  status: Status;
  color: string;
  reason: string;
  discharge_cfs: number | null;
  gage_height_ft: number | null;
  observed_at: string | null;
  age_minutes: number | null;
  percentile: number | null;
  trend: Trend;
  activity: Activity | null;
  thresholds: ActivityThresholds | null;
  available_parameters: string[];
  rating: StationRating | null;
  velocity_fps: number | null;
  velocity_mph: number | null;
  velocity_method: string | null;
  velocity_confidence: VelocityConfidence | null;
  velocity_note: string | null;
  cross_section_area_sqft: number | null;
}

export type SegmentFeature = Feature<MultiLineString, SegmentProperties>;
export type SiteFeature = Feature<Point, SiteProperties>;

interface CollectionMeta {
  basin: { huc8: string; name: string };
  activity: Activity;
  status_counts: Partial<Record<Status, number>>;
}

export type SegmentCollection = FeatureCollection<MultiLineString, SegmentProperties> &
  CollectionMeta & { computed_at: string | null };

export type SiteCollection = FeatureCollection<Point, SiteProperties> & CollectionMeta;

export interface SeriesPoint {
  time: string;
  value: number;
}

export interface SeriesResponse {
  site_id: string;
  parameter_code: string;
  unit: string;
  points: SeriesPoint[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  store_backend: string;
  checked_at: string;
  last_run: {
    run_id: string;
    started_at: string;
    finished_at: string | null;
    status: string;
    basins: string[];
    counts: Record<string, number>;
    error: string | null;
  } | null;
  last_run_age_minutes: number | null;
  stale: boolean;
  activities: Activity[];
}
