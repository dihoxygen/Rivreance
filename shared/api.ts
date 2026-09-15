import type {
  Activity,
  Basin,
  HealthResponse,
  SegmentCollection,
  SeriesResponse,
  SiteCollection,
} from "./types";

/** Matches the API's own cache window, so clients and the server agree on freshness. */
export const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface RivreanceApi {
  health: () => Promise<HealthResponse>;
  basins: () => Promise<Basin[]>;
  segments: (huc8: string, activity: Activity, minOrder?: number) => Promise<SegmentCollection>;
  sites: (huc8: string, activity: Activity) => Promise<SiteCollection>;
  series: (siteId: string, parameter: string) => Promise<SeriesResponse>;
}

/**
 * The web and mobile clients read the same endpoints but learn their base URL
 * differently (build-time env var vs. Expo app config), so the base URL is injected.
 */
export function createApi(baseUrl: string): RivreanceApi {
  const root = baseUrl.replace(/\/$/, "");

  async function getJson<T>(
    path: string,
    params?: Record<string, string | number>,
  ): Promise<T> {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      query.set(key, String(value));
    }
    const search = query.toString();
    const response = await fetch(`${root}${path}${search ? `?${search}` : ""}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new ApiError(`${path} responded ${response.status}`, response.status);
    }
    return (await response.json()) as T;
  }

  return {
    health: () => getJson<HealthResponse>("/health"),
    basins: () =>
      getJson<{ basins: Basin[] }>("/basins").then((payload) => payload.basins),
    segments: (huc8, activity, minOrder = 1) =>
      getJson<SegmentCollection>(`/basins/${huc8}/segments`, {
        activity,
        min_order: minOrder,
      }),
    sites: (huc8, activity) =>
      getJson<SiteCollection>(`/basins/${huc8}/sites`, { activity }),
    series: (siteId, parameter) =>
      getJson<SeriesResponse>(`/sites/${encodeURIComponent(siteId)}/series`, { parameter }),
  };
}

export const queryKeys = {
  health: ["health"] as const,
  basins: ["basins"] as const,
  segments: (huc8: string, activity: Activity) => ["segments", huc8, activity] as const,
  sites: (huc8: string, activity: Activity) => ["sites", huc8, activity] as const,
  series: (siteId: string, parameter: string) => ["series", siteId, parameter] as const,
};
