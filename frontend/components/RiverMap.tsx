"use client";

import type { FeatureCollection } from "geojson";
import maplibregl, {
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapMouseEvent,
} from "maplibre-gl";
import { useEffect, useRef } from "react";

import { buildMapStyle } from "@/lib/mapStyle";
import type { Basin, SegmentCollection, SiteCollection } from "@/lib/types";

const SEGMENT_SOURCE = "river-segments";
const SITE_SOURCE = "gage-sites";
const SEGMENT_HIT_LAYER = "river-segments-hit";
const SITE_LAYER = "gage-sites-circle";

const EMPTY_COLLECTION: FeatureCollection = { type: "FeatureCollection", features: [] };

interface RiverMapProps {
  basin: Basin;
  segments: SegmentCollection | undefined;
  sites: SiteCollection | undefined;
  selectedSiteId: string | null;
  onSelectSite: (siteId: string | null) => void;
}

export function RiverMap({
  basin,
  segments,
  sites,
  selectedSiteId,
  onSelectSite,
}: RiverMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const hoverPopupRef = useRef<maplibregl.Popup | null>(null);
  const onSelectSiteRef = useRef(onSelectSite);
  onSelectSiteRef.current = onSelectSite;

  // One-time map setup. Data arrives later through setData, so the map is never rebuilt.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildMapStyle(),
      bounds: basin.bbox,
      fitBoundsOptions: { padding: 48 },
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    const hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnMove: true,
      className: "segment-tooltip",
      offset: 8,
    });
    hoverPopupRef.current = hoverPopup;

    map.on("load", () => {
      map.addSource(SEGMENT_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
      map.addSource(SITE_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });

      // Casing only under classified reaches: on gray ones it reads as a black river.
      map.addLayer({
        id: "river-segments-casing",
        type: "line",
        source: SEGMENT_SOURCE,
        layout: { "line-cap": "round", "line-join": "round" },
        filter: ["!=", ["get", "status"], "gray"],
        paint: {
          "line-color": "#05080b",
          "line-opacity": 0.4,
          "line-width": ["+", ["get", "line_width"], 2],
        },
      });

      // Data-driven color: the API ships the traffic-light color on each feature.
      // Unclassified reaches stay thinner and softer so the colored ones lead the eye.
      const grayScale = (factor: number): ExpressionSpecification => [
        "*",
        ["get", "line_width"],
        ["case", ["==", ["get", "status"], "gray"], factor * 0.7, factor],
      ];
      map.addLayer({
        id: "river-segments-line",
        type: "line",
        source: SEGMENT_SOURCE,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-opacity": ["case", ["==", ["get", "status"], "gray"], 0.6, 0.95],
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            7,
            grayScale(0.6),
            11,
            grayScale(1),
            14,
            grayScale(2.2),
          ],
        },
      });

      // Invisible fat line so clicks and hovers are forgiving on thin creeks.
      map.addLayer({
        id: SEGMENT_HIT_LAYER,
        type: "line",
        source: SEGMENT_SOURCE,
        paint: { "line-color": "#000000", "line-opacity": 0, "line-width": 14 },
      });

      map.addLayer({
        id: "gage-sites-halo",
        type: "circle",
        source: SITE_SOURCE,
        paint: {
          "circle-radius": 16,
          "circle-color": ["get", "color"],
          "circle-opacity": 0.22,
          "circle-stroke-width": 0,
        },
        filter: ["==", ["get", "site_id"], ""],
      });

      map.addLayer({
        id: SITE_LAYER,
        type: "circle",
        source: SITE_SOURCE,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 5, 12, 9],
          "circle-color": ["get", "color"],
          "circle-stroke-color": "#f8fafc",
          "circle-stroke-width": 1.6,
        },
      });

      readyRef.current = true;
      map.fire("rivreance.ready");
    });

    const showTooltip = (event: MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(event.point, {
        layers: [SEGMENT_HIT_LAYER],
      })[0];
      if (!feature) {
        hoverPopup.remove();
        map.getCanvas().style.cursor = "";
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const properties = feature.properties as { name?: string | null; reason?: string };
      hoverPopup
        .setLngLat(event.lngLat)
        .setHTML(
          `<strong>${escapeHtml(properties.name ?? "Unnamed reach")}</strong><br />${escapeHtml(
            properties.reason ?? "",
          )}`,
        )
        .addTo(map);
    };

    map.on("mousemove", showTooltip);
    map.on("mouseout", () => hoverPopup.remove());

    map.on("click", (event) => {
      const site = map.queryRenderedFeatures(event.point, { layers: [SITE_LAYER] })[0];
      if (site) {
        onSelectSiteRef.current(String(site.properties?.site_id ?? ""));
        return;
      }
      const segment = map.queryRenderedFeatures(event.point, { layers: [SEGMENT_HIT_LAYER] })[0];
      const sourceSiteId = segment?.properties?.source_site_id;
      onSelectSiteRef.current(typeof sourceSiteId === "string" ? sourceSiteId : null);
    });

    return () => {
      hoverPopup.remove();
      readyRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, [basin.bbox]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.fitBounds(basin.bbox, { padding: 48, duration: 600 });
  }, [basin.bbox]);

  useEffect(() => {
    updateSource(mapRef.current, readyRef, SEGMENT_SOURCE, segments);
  }, [segments]);

  useEffect(() => {
    updateSource(mapRef.current, readyRef, SITE_SOURCE, sites);
  }, [sites]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyFilter = () => {
      if (!map.getLayer("gage-sites-halo")) return;
      map.setFilter("gage-sites-halo", ["==", ["get", "site_id"], selectedSiteId ?? ""]);
    };
    if (readyRef.current) applyFilter();
    else map.once("rivreance.ready", applyFilter);
  }, [selectedSiteId]);

  return <div ref={containerRef} className="map-canvas" data-testid="river-map" />;
}

function updateSource(
  map: maplibregl.Map | null,
  readyRef: { current: boolean },
  sourceId: string,
  data: SegmentCollection | SiteCollection | undefined,
) {
  if (!map || !data) return;
  const apply = () => {
    const source = map.getSource(sourceId) as GeoJSONSource | undefined;
    source?.setData(data);
  };
  if (readyRef.current) apply();
  else map.once("rivreance.ready", apply);
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ??
      character,
  );
}
