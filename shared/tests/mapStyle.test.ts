import {
  createExpression,
  featureFilter,
  latest,
  validateStyleMin,
} from "@maplibre/maplibre-gl-style-spec";
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildMapStyle,
  SEGMENT_CASING_FILTER,
  SEGMENT_CASING_WIDTH,
  SEGMENT_COLOR,
  SEGMENT_OPACITY,
  SEGMENT_WIDTH,
  siteHaloFilter,
  SITE_RADIUS,
  SITE_RADIUS_TOUCH,
  type StyleExpression,
} from "../mapStyle.ts";

/**
 * The web and native maps declare their layers from these expressions, so they are
 * evaluated here with MapLibre's own expression engine rather than re-implemented.
 * A regression in the shared expressions would otherwise only show up on a device.
 */
function evaluator(specPath: "line-color" | "line-opacity" | "line-width" | "circle-radius") {
  const spec =
    specPath === "circle-radius"
      ? latest.paint_circle["circle-radius"]
      : latest.paint_line[specPath];

  return (expr: StyleExpression, zoom: number, properties: Record<string, unknown>) => {
    const compiled = createExpression(expr, `layers[0].paint.${specPath}`, spec as never);
    assert.equal(compiled.result, "success", `failed to compile ${specPath}`);
    if (compiled.result !== "success") throw new Error("unreachable");
    return compiled.value.evaluate({ zoom }, { type: "LineString", properties } as never);
  };
}

const segment = (status: string, color: string, lineWidth = 2) => ({
  status,
  color,
  line_width: lineWidth,
});

describe("basemap style", () => {
  it("is a valid MapLibre style", () => {
    const style = buildMapStyle();
    assert.notEqual(typeof style, "string");
    assert.deepEqual(validateStyleMin(style as never), []);
  });

  it("uses a MapTiler style URL when a key is supplied", () => {
    assert.equal(
      buildMapStyle("test-key"),
      "https://api.maptiler.com/maps/outdoor-v2/style.json?key=test-key",
    );
  });
});

const TRAFFIC_LIGHT = [
  ["green", "#1a9850"],
  ["yellow", "#f6c344"],
  ["red", "#d73027"],
  ["gray", "#9aa0a6"],
] as const;

/** MapLibre parses colours into channels, so expectations are compared in that form. */
function hexToRgba(hex: string): string {
  const channel = (at: number) => Number.parseInt(hex.slice(at, at + 2), 16);
  return `rgba(${channel(1)},${channel(3)},${channel(5)},1)`;
}

describe("segment colouring", () => {
  const color = evaluator("line-color");

  it("takes the traffic-light colour the API computed", () => {
    for (const [status, hex] of TRAFFIC_LIGHT) {
      assert.equal(
        color(SEGMENT_COLOR, 11, segment(status, hex)).toString(),
        hexToRgba(hex),
        `${status} should render as ${hex}`,
      );
    }
  });

  it("keeps the four statuses visually distinct", () => {
    const rendered = new Set(
      TRAFFIC_LIGHT.map(([status, hex]) => color(SEGMENT_COLOR, 11, segment(status, hex)).toString()),
    );
    assert.equal(rendered.size, TRAFFIC_LIGHT.length);
  });
});

describe("segment emphasis", () => {
  const opacity = evaluator("line-opacity");
  const width = evaluator("line-width");

  it("fades unclassified reaches so coloured ones lead the eye", () => {
    assert.equal(opacity(SEGMENT_OPACITY, 11, segment("gray", "#9aa0a6")), 0.6);
    for (const status of ["green", "yellow", "red"]) {
      assert.equal(opacity(SEGMENT_OPACITY, 11, segment(status, "#1a9850")), 0.95);
    }
  });

  it("draws unclassified reaches thinner at every zoom", () => {
    for (const zoom of [7, 9, 11, 14, 16]) {
      const gray = width(SEGMENT_WIDTH, zoom, segment("gray", "#9aa0a6"));
      const green = width(SEGMENT_WIDTH, zoom, segment("green", "#1a9850"));
      assert.ok(gray < green, `gray should be thinner than green at zoom ${zoom}`);
      assert.equal(Number(gray.toFixed(6)), Number((green * 0.7).toFixed(6)));
    }
  });

  it("thickens reaches as the map zooms in", () => {
    const widths = [7, 11, 14].map((zoom) =>
      width(SEGMENT_WIDTH, zoom, segment("green", "#1a9850")),
    );
    assert.deepEqual(widths, [...widths].sort((a, b) => a - b));
    assert.ok(widths[0]! < widths[2]!);
  });

  it("scales width with the stream order the API encoded", () => {
    const creek = width(SEGMENT_WIDTH, 11, segment("green", "#1a9850", 1));
    const river = width(SEGMENT_WIDTH, 11, segment("green", "#1a9850", 4));
    assert.ok(river > creek);
  });

  it("draws the casing wider than the line it sits under", () => {
    const casing = width(SEGMENT_CASING_WIDTH, 11, segment("green", "#1a9850"));
    const line = width(SEGMENT_WIDTH, 11, segment("green", "#1a9850"));
    assert.ok(casing > line);
  });
});

describe("filters", () => {
  const matches = (expr: StyleExpression, properties: Record<string, unknown>) =>
    featureFilter(expr as never, "layers[0].filter").filter({ zoom: 11 }, {
      type: 2,
      properties,
    } as never);

  it("keeps the casing off gray reaches, where it would read as a black river", () => {
    assert.equal(matches(SEGMENT_CASING_FILTER, { status: "gray" }), false);
    for (const status of ["green", "yellow", "red"]) {
      assert.equal(matches(SEGMENT_CASING_FILTER, { status }), true);
    }
  });

  it("haloes only the selected gage", () => {
    assert.equal(matches(siteHaloFilter("USGS-02458450"), { site_id: "USGS-02458450" }), true);
    assert.equal(matches(siteHaloFilter("USGS-02458450"), { site_id: "USGS-02461500" }), false);
  });

  it("haloes nothing when no gage is selected", () => {
    assert.equal(matches(siteHaloFilter(null), { site_id: "USGS-02458450" }), false);
  });
});

describe("gage markers", () => {
  const radius = evaluator("circle-radius");

  it("gives touch screens a larger target than a mouse cursor needs", () => {
    for (const zoom of [7, 10, 12, 15]) {
      const web = radius(SITE_RADIUS, zoom, {});
      const touch = radius(SITE_RADIUS_TOUCH, zoom, {});
      assert.ok(touch > web, `touch radius should exceed web radius at zoom ${zoom}`);
    }
  });
});
