import {
  Camera,
  GeoJSONSource,
  Layer,
  Map,
  type PressEventWithFeatures,
} from "@maplibre/maplibre-react-native";
import { useMemo } from "react";
import type { NativeSyntheticEvent } from "react-native";
import { StyleSheet } from "react-native";

import {
  buildMapStyle,
  segment as segmentStyle,
  SEGMENT_SOURCE_ID,
  site as siteStyle,
  SITE_SOURCE_ID,
} from "@/lib/mapStyle";
import { theme } from "@/lib/theme";
import type { Basin, SegmentCollection, SiteCollection } from "@shared/types";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Keeps the fitted basin clear of the floating header and legend overlays. */
const CAMERA_PADDING = { top: 150, right: 24, bottom: 130, left: 24 };

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
  const mapStyle = useMemo(() => buildMapStyle(), []);

  const handleSitePress = (event: NativeSyntheticEvent<PressEventWithFeatures>) => {
    const siteId = event.nativeEvent.features[0]?.properties?.site_id;
    onSelectSite(typeof siteId === "string" ? siteId : null);
  };

  /** Tapping a reach opens the gage it took its color from, so the color is explainable. */
  const handleSegmentPress = (event: NativeSyntheticEvent<PressEventWithFeatures>) => {
    const sourceSiteId = event.nativeEvent.features[0]?.properties?.source_site_id;
    onSelectSite(typeof sourceSiteId === "string" ? sourceSiteId : null);
  };

  return (
    <Map
      style={styles.map}
      mapStyle={mapStyle}
      logo={false}
      attributionPosition={{ bottom: 8, right: 8 }}
      compassPosition={{ top: 8, right: 8 }}
      onPress={() => onSelectSite(null)}
    >
      <Camera
        initialViewState={{ bounds: basin.bbox, padding: CAMERA_PADDING }}
        bounds={basin.bbox}
        padding={CAMERA_PADDING}
        duration={600}
      />

      <GeoJSONSource
        id={SEGMENT_SOURCE_ID}
        data={segments ?? EMPTY}
        onPress={handleSegmentPress}
      >
        <Layer
          id="river-segments-casing"
          type="line"
          filter={segmentStyle.casingFilter}
          layout={{ "line-cap": "round", "line-join": "round" }}
          paint={{
            "line-color": segmentStyle.casingColor,
            "line-opacity": segmentStyle.casingOpacity,
            "line-width": segmentStyle.casingWidth,
          }}
        />
        <Layer
          id="river-segments-line"
          type="line"
          layout={{ "line-cap": "round", "line-join": "round" }}
          paint={{
            "line-color": segmentStyle.color,
            "line-opacity": segmentStyle.opacity,
            "line-width": segmentStyle.width,
          }}
        />
      </GeoJSONSource>

      <GeoJSONSource id={SITE_SOURCE_ID} data={sites ?? EMPTY} onPress={handleSitePress}>
        <Layer
          id="gage-sites-halo"
          type="circle"
          filter={siteStyle.haloFilter(selectedSiteId)}
          paint={{
            "circle-radius": siteStyle.haloRadius,
            "circle-color": siteStyle.color,
            "circle-opacity": siteStyle.haloOpacity,
            "circle-stroke-width": 0,
          }}
        />
        <Layer
          id="gage-sites-circle"
          type="circle"
          paint={{
            "circle-radius": siteStyle.radius,
            "circle-color": siteStyle.color,
            "circle-stroke-color": siteStyle.strokeColor,
            "circle-stroke-width": 1.6,
          }}
        />
      </GeoJSONSource>
    </Map>
  );
}

const styles = StyleSheet.create({
  map: { flex: 1, backgroundColor: theme.color.bg },
});
