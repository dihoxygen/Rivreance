import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { MAP_ATTRIBUTION_NOTE } from "@/lib/mapStyle";
import { theme } from "@/lib/theme";
import { STATUS_COLORS, STATUS_DESCRIPTIONS, STATUS_LABELS } from "@shared/format";
import type { Status } from "@shared/types";

const ORDER: Status[] = ["green", "yellow", "red", "gray"];

interface LegendProps {
  statusCounts: Partial<Record<Status, number>>;
}

/** Collapsed by default on phones, where the map itself is the scarce resource. */
export function Legend({ statusCounts }: LegendProps) {
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.legend}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((value) => !value)}
        style={styles.toggle}
      >
        <Text style={styles.toggleText}>Legend</Text>
        <Text style={styles.toggleText}>{open ? "▾" : "▴"}</Text>
      </Pressable>

      {open ? (
        <View style={styles.body}>
          {ORDER.map((status) => (
            <View key={status} style={styles.row}>
              <View style={[styles.swatch, { backgroundColor: STATUS_COLORS[status] }]} />
              <View style={styles.rowText}>
                <Text style={styles.label}>
                  {STATUS_LABELS[status]}
                  {statusCounts[status] ? ` · ${statusCounts[status]} reaches` : ""}
                </Text>
                <Text style={styles.muted}>{STATUS_DESCRIPTIONS[status]}</Text>
              </View>
            </View>
          ))}
          <Text style={styles.muted}>
            Reaches take the status of the gage on their mainstem, or of a gage within 5 km.
            Estimates are not safety advice. {MAP_ATTRIBUTION_NOTE}.
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  legend: {
    backgroundColor: theme.color.bgElevated,
    borderColor: theme.color.border,
    borderWidth: 1,
    borderRadius: theme.radius,
    overflow: "hidden",
    maxWidth: 320,
  },
  toggle: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  toggleText: { color: theme.color.text, fontSize: 13, fontWeight: "600" },
  body: { paddingHorizontal: 12, paddingBottom: 12, gap: 10 },
  row: { flexDirection: "row", gap: 10 },
  rowText: { flex: 1 },
  swatch: { width: 12, height: 12, borderRadius: 3, marginTop: 3 },
  label: { color: theme.color.text, fontSize: 13, fontWeight: "600" },
  muted: { color: theme.color.textMuted, fontSize: 12, lineHeight: 17 },
});
