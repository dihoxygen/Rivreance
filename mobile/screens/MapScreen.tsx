import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ActivityToggle } from "@/components/ActivityToggle";
import { Legend } from "@/components/Legend";
import { RiverMap } from "@/components/RiverMap";
import { SiteSheet } from "@/components/SiteSheet";
import { StatusBanner } from "@/components/StatusBanner";
import { api, queryKeys } from "@/lib/api";
import { theme } from "@/lib/theme";
import { STATUS_COLORS, STATUS_LABELS } from "@shared/format";
import type { Activity, Status } from "@shared/types";

const STATUS_ORDER: Status[] = ["green", "yellow", "red", "gray"];

export function MapScreen() {
  const insets = useSafeAreaInsets();
  const [activity, setActivity] = useState<Activity>("kayaking");
  const [basinIndex, setBasinIndex] = useState(0);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);

  const health = useQuery({ queryKey: queryKeys.health, queryFn: api.health });
  const basins = useQuery({ queryKey: queryKeys.basins, queryFn: api.basins });
  const basin = basins.data?.[Math.min(basinIndex, (basins.data?.length ?? 1) - 1)];

  const segments = useQuery({
    queryKey: queryKeys.segments(basin?.huc8 ?? "", activity),
    queryFn: () => api.segments(basin!.huc8, activity),
    enabled: Boolean(basin),
  });
  const sites = useQuery({
    queryKey: queryKeys.sites(basin?.huc8 ?? "", activity),
    queryFn: () => api.sites(basin!.huc8, activity),
    enabled: Boolean(basin),
  });

  const selectedSite = useMemo(
    () =>
      sites.data?.features.find((feature) => feature.properties.site_id === selectedSiteId)
        ?.properties ?? null,
    [sites.data, selectedSiteId],
  );

  const gageCounts = sites.data?.status_counts ?? {};

  return (
    <View style={styles.screen}>
      {basin ? (
        <RiverMap
          basin={basin}
          segments={segments.data}
          sites={sites.data}
          selectedSiteId={selectedSiteId}
          onSelectSite={setSelectedSiteId}
        />
      ) : (
        <View style={styles.placeholder}>
          <Text style={styles.muted}>
            {basins.isError ? "Could not load basins from the API." : "Loading map…"}
          </Text>
        </View>
      )}

      {/* Overlays float above the map, inset out of the notch and home indicator. */}
      <View style={[styles.top, { paddingTop: insets.top + 8 }]} pointerEvents="box-none">
        <View style={styles.topRow}>
          <View style={styles.brand}>
            <Text style={styles.brandName}>Rivreance</Text>
            <Text style={styles.muted} numberOfLines={1}>
              {basin ? `${basin.name} · HUC ${basin.huc8}` : "Loading basins…"}
            </Text>
          </View>
          <ActivityToggle value={activity} onChange={setActivity} />
        </View>

        {basins.data && basins.data.length > 1 ? (
          <View style={styles.basinRow}>
            {basins.data.map((option, index) => {
              const active = index === basinIndex;
              return (
                <Pressable
                  key={option.huc8}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  onPress={() => {
                    setBasinIndex(index);
                    setSelectedSiteId(null);
                  }}
                  style={[styles.chip, active && styles.chipActive]}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>
                    {option.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        <StatusBanner
          health={health.data}
          isError={health.isError}
          computedAt={segments.data?.computed_at}
        />
      </View>

      <View style={[styles.bottom, { paddingBottom: insets.bottom + 12 }]} pointerEvents="box-none">
        <View style={styles.summary}>
          <Text style={styles.summaryTitle}>
            {sites.data?.features.length ?? 0} gages ·{" "}
            {activity === "kayaking" ? "paddling" : "fishing"}
          </Text>
          <View style={styles.summaryRow}>
            {STATUS_ORDER.filter((status) => gageCounts[status]).map((status) => (
              <View key={status} style={styles.summaryItem}>
                <View style={[styles.dot, { backgroundColor: STATUS_COLORS[status] }]} />
                <Text style={styles.muted}>
                  {gageCounts[status]} {STATUS_LABELS[status].toLowerCase()}
                </Text>
              </View>
            ))}
          </View>
          {segments.isPending || sites.isPending ? (
            <Text style={styles.muted}>Loading conditions…</Text>
          ) : null}
        </View>

        <Legend statusCounts={segments.data?.status_counts ?? {}} />
      </View>

      {selectedSite ? (
        <SiteSheet site={selectedSite} onClose={() => setSelectedSiteId(null)} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.color.bg },
  placeholder: { flex: 1, alignItems: "center", justifyContent: "center" },
  top: { position: "absolute", top: 0, left: 0, right: 0, paddingHorizontal: 12, gap: 8 },
  topRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  brand: {
    flex: 1,
    backgroundColor: theme.color.bgElevated,
    borderColor: theme.color.border,
    borderWidth: 1,
    borderRadius: theme.radius,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  brandName: { color: theme.color.text, fontSize: 16, fontWeight: "700" },
  basinRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  chip: {
    backgroundColor: theme.color.bgElevated,
    borderColor: theme.color.border,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipActive: { borderColor: theme.color.accent },
  chipText: { color: theme.color.textMuted, fontSize: 12, fontWeight: "600" },
  chipTextActive: { color: theme.color.text },
  bottom: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 12,
    gap: 8,
    alignItems: "flex-start",
  },
  summary: {
    backgroundColor: theme.color.bgElevated,
    borderColor: theme.color.border,
    borderWidth: 1,
    borderRadius: theme.radius,
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 4,
    maxWidth: 320,
  },
  summaryTitle: { color: theme.color.text, fontSize: 13, fontWeight: "600" },
  summaryRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  summaryItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  muted: { color: theme.color.textMuted, fontSize: 12 },
});
