import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, queryKeys, REFRESH_INTERVAL_MS } from "@/lib/api";
import { theme } from "@/lib/theme";
import { TrendChart } from "./TrendChart";
import {
  CONFIDENCE_LABELS,
  formatAge,
  formatClock,
  formatFlow,
  formatNumber,
  formatOrdinal,
  STATUS_COLORS,
  STATUS_LABELS,
  TREND_ICONS,
  TREND_LABELS,
  VELOCITY_METHOD_LABELS,
} from "@shared/format";
import type { ActivityThresholds, SiteProperties } from "@shared/types";

const PARAMETER_LABELS: Record<string, { label: string; unit: string }> = {
  "00060": { label: "Discharge", unit: "cfs" },
  "00065": { label: "Gage height", unit: "ft" },
};

interface SiteSheetProps {
  site: SiteProperties;
  onClose: () => void;
}

export function SiteSheet({ site, onClose }: SiteSheetProps) {
  const insets = useSafeAreaInsets();
  const parameters = site.available_parameters.filter((code) => code in PARAMETER_LABELS);
  const [parameter, setParameter] = useState(parameters[0] ?? "00060");
  const activeParameter = parameters.includes(parameter) ? parameter : (parameters[0] ?? "00060");

  const series = useQuery({
    queryKey: queryKeys.series(site.site_id, activeParameter),
    queryFn: () => api.series(site.site_id, activeParameter),
    enabled: parameters.length > 0,
    staleTime: REFRESH_INTERVAL_MS,
    retry: false,
  });

  const parameterMeta = PARAMETER_LABELS[activeParameter] ?? { label: "Value", unit: "" };

  return (
    <View style={[styles.sheet, { paddingBottom: insets.bottom + 12 }]}>
      <View style={styles.grabber} />

      <View style={styles.header}>
        <View style={styles.headerText}>
          <View style={[styles.pill, { backgroundColor: STATUS_COLORS[site.status] }]}>
            <Text style={styles.pillText}>{STATUS_LABELS[site.status]}</Text>
          </View>
          <Text style={styles.title}>{site.name}</Text>
          <Text style={styles.muted}>
            USGS {site.site_number}
            {site.drainage_area_sqmi
              ? ` · ${formatNumber(site.drainage_area_sqmi, 0)} sq mi drainage`
              : ""}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close gage details"
          hitSlop={12}
          onPress={onClose}
          style={styles.close}
        >
          <Text style={styles.closeText}>✕</Text>
        </Pressable>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.reason}>{site.reason}</Text>

        <View style={styles.metrics}>
          <Metric label="Discharge" value={formatFlow(site.discharge_cfs)} />
          <Metric
            label="Gage height"
            value={
              site.gage_height_ft === null ? "—" : `${formatNumber(site.gage_height_ft, 2)} ft`
            }
          />
          <Metric
            label="Velocity"
            value={site.velocity_mph === null ? "—" : `${formatNumber(site.velocity_mph, 2)} mph`}
            hint={
              site.velocity_fps === null ? undefined : `${formatNumber(site.velocity_fps, 2)} fps`
            }
          />
          <Metric
            label="Trend (3 h)"
            value={`${TREND_ICONS[site.trend]} ${TREND_LABELS[site.trend]}`}
          />
          <Metric
            label="Percentile"
            value={formatOrdinal(site.percentile)}
            hint="of the recent record"
          />
          <Metric
            label="Reading age"
            value={formatAge(site.age_minutes)}
            hint={formatClock(site.observed_at)}
          />
        </View>

        {site.thresholds && site.discharge_cfs !== null ? (
          <ThresholdBar thresholds={site.thresholds} value={site.discharge_cfs} />
        ) : null}

        {site.velocity_method ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>How velocity was estimated</Text>
            <Text style={styles.body}>
              {VELOCITY_METHOD_LABELS[site.velocity_method] ?? site.velocity_method}
              {site.velocity_confidence
                ? ` · ${CONFIDENCE_LABELS[site.velocity_confidence]}`
                : ""}
            </Text>
            {site.velocity_note ? <Text style={styles.muted}>{site.velocity_note}</Text> : null}
            {site.cross_section_area_sqft ? (
              <Text style={styles.muted}>
                Implied cross-sectional area {formatNumber(site.cross_section_area_sqft, 0)} ft²
              </Text>
            ) : null}
          </View>
        ) : null}

        {parameters.length > 0 ? (
          <View style={styles.section}>
            <View style={styles.sectionHead}>
              <Text style={styles.sectionTitle}>Last 24 hours</Text>
              {parameters.length > 1 ? (
                <View style={styles.miniToggle}>
                  {parameters.map((code) => {
                    const active = code === activeParameter;
                    return (
                      <Pressable
                        key={code}
                        accessibilityRole="button"
                        accessibilityState={{ selected: active }}
                        onPress={() => setParameter(code)}
                        style={[styles.miniOption, active && styles.miniOptionActive]}
                      >
                        <Text style={[styles.miniLabel, active && styles.miniLabelActive]}>
                          {PARAMETER_LABELS[code]?.label ?? code}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : null}
            </View>
            {series.isPending ? <Text style={styles.muted}>Loading readings…</Text> : null}
            {series.isError ? (
              <Text style={styles.muted}>No cached readings for this parameter.</Text>
            ) : null}
            {series.data ? (
              <TrendChart
                points={series.data.points}
                unit={series.data.unit || parameterMeta.unit}
                color={STATUS_COLORS[site.status]}
                label={parameterMeta.label}
              />
            ) : null}
          </View>
        ) : null}

        <Pressable
          accessibilityRole="link"
          onPress={() =>
            Linking.openURL(
              `https://waterdata.usgs.gov/monitoring-location/${site.site_number}/`,
            )
          }
        >
          <Text style={styles.link}>Open the USGS station page →</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>
        {value}
        {hint ? <Text style={styles.muted}> {hint}</Text> : null}
      </Text>
    </View>
  );
}

function ThresholdBar({
  thresholds,
  value,
}: {
  thresholds: ActivityThresholds;
  value: number;
}) {
  const domainMax = Math.max(thresholds.max_cfs * 1.2, value * 1.05);
  const share = (from: number, to: number) => Math.max(0, (to - from) / domainMax);
  const markerLeft = `${Math.min(100, Math.max(0, (value / domainMax) * 100))}%` as const;

  const bands: { flex: number; color: string }[] = [
    { flex: share(0, thresholds.min_cfs), color: STATUS_COLORS.red },
    { flex: share(thresholds.min_cfs, thresholds.opt_min_cfs), color: STATUS_COLORS.yellow },
    { flex: share(thresholds.opt_min_cfs, thresholds.opt_max_cfs), color: STATUS_COLORS.green },
    { flex: share(thresholds.opt_max_cfs, thresholds.max_cfs), color: STATUS_COLORS.yellow },
    { flex: share(thresholds.max_cfs, domainMax), color: STATUS_COLORS.red },
  ];

  return (
    <View style={styles.section}>
      <View style={styles.sectionHead}>
        <Text style={styles.sectionTitle}>
          {thresholds.activity === "kayaking" ? "Paddling" : "Fishing"} flow window
        </Text>
        <Text style={styles.muted}>{thresholds.source.replace(/_/g, " ")}</Text>
      </View>

      <View
        accessibilityRole="image"
        accessibilityLabel="Flow window with current reading"
        style={styles.bar}
      >
        {bands.map((band, index) => (
          <View key={index} style={{ flex: band.flex, backgroundColor: band.color }} />
        ))}
        <View style={[styles.marker, { left: markerLeft }]} />
      </View>

      <View style={styles.scale}>
        <Text style={styles.muted}>{formatFlow(thresholds.min_cfs)} min</Text>
        <Text style={styles.muted}>
          {formatFlow(thresholds.opt_min_cfs)}–{formatFlow(thresholds.opt_max_cfs)} optimal
        </Text>
        <Text style={styles.muted}>{formatFlow(thresholds.max_cfs)} max</Text>
      </View>
      {thresholds.note ? <Text style={styles.muted}>{thresholds.note}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: "72%",
    backgroundColor: theme.color.bgElevated,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderTopWidth: 1,
    borderColor: theme.color.border,
    paddingHorizontal: 16,
  },
  grabber: {
    alignSelf: "center",
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.color.border,
    marginTop: 8,
  },
  header: { flexDirection: "row", alignItems: "flex-start", gap: 12, paddingTop: 10 },
  headerText: { flex: 1, gap: 4 },
  pill: { alignSelf: "flex-start", borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  pillText: { color: "#04121c", fontSize: 11, fontWeight: "700" },
  title: { color: theme.color.text, fontSize: 17, fontWeight: "700" },
  close: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 16,
    backgroundColor: theme.color.surface,
  },
  closeText: { color: theme.color.textMuted, fontSize: 14 },
  scroll: { marginTop: 12 },
  scrollContent: { gap: 14, paddingBottom: 4 },
  reason: { color: theme.color.text, fontSize: 14, lineHeight: 20 },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  metric: {
    flexGrow: 1,
    flexBasis: "45%",
    backgroundColor: theme.color.surface,
    borderRadius: 10,
    padding: 10,
    gap: 2,
  },
  metricLabel: { color: theme.color.textMuted, fontSize: 11, textTransform: "uppercase" },
  metricValue: { color: theme.color.text, fontSize: 15, fontWeight: "600" },
  section: { gap: 6 },
  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  sectionTitle: { color: theme.color.text, fontSize: 13, fontWeight: "700" },
  body: { color: theme.color.text, fontSize: 13 },
  muted: { color: theme.color.textMuted, fontSize: 12, lineHeight: 17 },
  miniToggle: {
    flexDirection: "row",
    backgroundColor: theme.color.surface,
    borderRadius: 999,
    padding: 2,
  },
  miniOption: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  miniOptionActive: { backgroundColor: theme.color.accent },
  miniLabel: { color: theme.color.textMuted, fontSize: 11, fontWeight: "600" },
  miniLabelActive: { color: "#04121c" },
  bar: {
    flexDirection: "row",
    height: 12,
    borderRadius: 6,
    overflow: "hidden",
    position: "relative",
  },
  marker: {
    position: "absolute",
    top: -3,
    width: 2,
    height: 18,
    marginLeft: -1,
    backgroundColor: theme.color.text,
  },
  scale: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  link: { color: theme.color.accent, fontSize: 13, fontWeight: "600", paddingVertical: 4 },
});
