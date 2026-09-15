import type { StyleSpecification } from "maplibre-gl";

/**
 * Basemap. USGS publishes public-domain topo tiles that need no API key and suit an
 * outdoor map, so they are the default. Set `NEXT_PUBLIC_MAPTILER_KEY` to swap in
 * MapTiler's vector Outdoor style instead.
 */
const USGS_TOPO_TILES =
  "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}";

const USGS_ATTRIBUTION =
  '<a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noreferrer">USGS The National Map</a>';

export const MAP_ATTRIBUTION_NOTE = "Conditions derived from USGS Water Data · Basemap USGS";

export function buildMapStyle(): StyleSpecification | string {
  const maptilerKey = process.env.NEXT_PUBLIC_MAPTILER_KEY;
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
