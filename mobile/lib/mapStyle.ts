import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";
import type { FilterSpecification, StyleSpecification } from "@maplibre/maplibre-react-native";

import * as style from "@shared/mapStyle";

/** Casts the shared, platform-neutral expressions into MapLibre's types once. */
const expression = (value: style.StyleExpression) => value as unknown as ExpressionSpecification;
const filter = (value: style.StyleExpression) => value as unknown as FilterSpecification;

export function buildMapStyle(): StyleSpecification | string {
  return style.buildMapStyle(process.env.EXPO_PUBLIC_MAPTILER_KEY) as StyleSpecification | string;
}

export const segment = {
  color: expression(style.SEGMENT_COLOR),
  opacity: expression(style.SEGMENT_OPACITY),
  width: expression(style.SEGMENT_WIDTH),
  casingColor: style.SEGMENT_CASING_COLOR,
  casingOpacity: style.SEGMENT_CASING_OPACITY,
  casingWidth: expression(style.SEGMENT_CASING_WIDTH),
  casingFilter: filter(style.SEGMENT_CASING_FILTER),
  hitWidth: style.SEGMENT_HIT_WIDTH,
};

export const site = {
  color: expression(style.SITE_COLOR),
  strokeColor: style.SITE_STROKE_COLOR,
  /** Fingers are blunter than cursors, so gage dots are drawn larger than on the web. */
  radius: expression(style.SITE_RADIUS_TOUCH),
  haloRadius: style.SITE_HALO_RADIUS,
  haloOpacity: style.SITE_HALO_OPACITY,
  haloFilter: (selectedSiteId: string | null) => filter(style.siteHaloFilter(selectedSiteId)),
};

export const { MAP_ATTRIBUTION_NOTE, SEGMENT_SOURCE_ID, SITE_SOURCE_ID } = style;
