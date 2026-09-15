/**
 * Basemap and data-driven layer styling shared by the web and mobile maps.
 *
 * MapLibre GL JS and MapLibre React Native consume the same style specification but
 * expose it through different TypeScript universes (kebab-case `paint` objects vs.
 * camelCase `style` props), so expressions are declared here in a neutral form and
 * each platform's wrapper casts them once.
 */

export type StyleExpression = [string, ...StyleValue[]];
export type StyleValue = string | number | boolean | null | StyleExpression;

export interface BasemapStyle {
  version: 8;
  sources: Record<
    string,
    {
      type: "raster";
      tiles: string[];
      tileSize: number;
      maxzoom: number;
      attribution: string;
    }
  >;
  layers: (
    | { id: string; type: "background"; paint: { "background-color": string } }
    | {
        id: string;
        type: "raster";
        source: string;
        paint: { "raster-opacity": number; "raster-saturation": number };
      }
  )[];
}

/**
 * USGS publishes public-domain topo tiles that need no API key and suit an outdoor
 * map, so they are the default. Supplying a MapTiler key swaps in their vector
 * Outdoor style instead.
 */
const USGS_TOPO_TILES =
  "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}";

const USGS_ATTRIBUTION =
  '<a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noreferrer">USGS The National Map</a>';

export const MAP_ATTRIBUTION_NOTE = "Conditions derived from USGS Water Data · Basemap USGS";

export function buildMapStyle(maptilerKey?: string): BasemapStyle | string {
  if (maptilerKey) {
    return `https://api.maptiler.com/maps/outdoor-v2/style.json?key=${maptilerKey}`;
  }
  return {
    version: 8,
    sources: {
      "usgs-topo": {
        type: "raster",
        tiles: [USGS_TOPO_TILES],
        tileSize: 256,
        maxzoom: 16,
        attribution: USGS_ATTRIBUTION,
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#0c1116" } },
      {
        id: "usgs-topo",
        type: "raster",
        source: "usgs-topo",
        paint: { "raster-opacity": 0.85, "raster-saturation": -0.15 },
      },
    ],
  };
}

export const SEGMENT_SOURCE_ID = "river-segments";
export const SITE_SOURCE_ID = "gage-sites";

/** The API ships the traffic-light color on each feature, so the map just reads it. */
export const SEGMENT_COLOR: StyleExpression = ["get", "color"];

/** Unclassified reaches recede so the colored ones lead the eye. */
export const SEGMENT_OPACITY: StyleExpression = [
  "case",
  ["==", ["get", "status"], "gray"],
  0.6,
  0.95,
];

export const SEGMENT_CASING_COLOR = "#05080b";
export const SEGMENT_CASING_OPACITY = 0.4;

/** Casing only under classified reaches: on gray ones it reads as a black river. */
export const SEGMENT_CASING_FILTER: StyleExpression = ["!=", ["get", "status"], "gray"];

export const SEGMENT_CASING_WIDTH: StyleExpression = ["+", ["get", "line_width"], 2];

function scaledWidth(factor: number): StyleExpression {
  return [
    "*",
    ["get", "line_width"],
    ["case", ["==", ["get", "status"], "gray"], factor * 0.7, factor],
  ];
}

/** Reaches thicken with zoom so a basin overview and a creek close-up both read well. */
export const SEGMENT_WIDTH: StyleExpression = [
  "interpolate",
  ["linear"],
  ["zoom"],
  7,
  scaledWidth(0.6),
  11,
  scaledWidth(1),
  14,
  scaledWidth(2.2),
];

/** Invisible fat line so taps and hovers are forgiving on thin creeks. */
export const SEGMENT_HIT_WIDTH = 14;

export const SITE_COLOR: StyleExpression = ["get", "color"];
export const SITE_STROKE_COLOR = "#f8fafc";

export const SITE_RADIUS: StyleExpression = [
  "interpolate",
  ["linear"],
  ["zoom"],
  7,
  5,
  12,
  9,
];

/** Touch targets need to be larger than a mouse cursor's. */
export const SITE_RADIUS_TOUCH: StyleExpression = [
  "interpolate",
  ["linear"],
  ["zoom"],
  7,
  7,
  12,
  12,
];

export const SITE_HALO_RADIUS = 16;
export const SITE_HALO_OPACITY = 0.22;

/** Matches only the selected gage; an empty id hides the halo entirely. */
export function siteHaloFilter(selectedSiteId: string | null): StyleExpression {
  return ["==", ["get", "site_id"], selectedSiteId ?? ""];
}
