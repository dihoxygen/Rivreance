import type {
  Activity,
  Basin,
  HealthResponse,
  SegmentCollection,
  SeriesResponse,
  SiteCollection,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** Matches the API's own cache window, so browsers and the server agree on freshness. */
export const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    url.searchParams.set(key, String(value));
  }
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new ApiError(`${path} responded ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJson<HealthResponse>("/health"),
  basins: () => getJson<{ basins: Basin[] }>("/basins").then((payload) => payload.basins),
  segments: (huc8: string, activity: Activity, minOrder = 1) =>
    getJson<SegmentCollection>(`/basins/${huc8}/segments`, {
      activity,
      min_order: minOrder,
    }),
  sites: (huc8: string, activity: Activity) =>
    getJson<SiteCollection>(`/basins/${huc8}/sites`, { activity }),
  series: (siteId: string, parameter: string) =>
    getJson<SeriesResponse>(`/sites/${encodeURIComponent(siteId)}/series`, { parameter }),
};

export const queryKeys = {
  health: ["health"] as const,
  basins: ["basins"] as const,
  segments: (huc8: string, activity: Activity) => ["segments", huc8, activity] as const,
  sites: (huc8: string, activity: Activity) => ["sites", huc8, activity] as const,
  series: (siteId: string, parameter: string) => ["series", siteId, parameter] as const,
};

export { ApiError };
