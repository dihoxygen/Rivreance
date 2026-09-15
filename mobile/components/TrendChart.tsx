import { useState } from "react";
import { StyleSheet, Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";

import { theme } from "@/lib/theme";
import { formatNumber, formatTimeOfDay } from "@shared/format";
import type { SeriesPoint } from "@shared/types";

const HEIGHT = 130;

interface TrendChartProps {
  points: SeriesPoint[];
  unit: string;
  color: string;
  label: string;
}

/**
 * Recharts is DOM-only, so the native trend is drawn directly with react-native-svg.
 * The shape is deliberately the same as the web chart: filled area under a stroked line.
 */
export function TrendChart({ points, unit, color, label }: TrendChartProps) {
  const [width, setWidth] = useState(0);

  const onLayout = (event: LayoutChangeEvent) => {
    setWidth(event.nativeEvent.layout.width);
  };

  if (points.length < 2) {
    return <Text style={styles.muted}>Not enough recent readings to chart.</Text>;
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A dead-flat series would divide by zero, so give it an arbitrary band to sit inside.
  const span = max - min || Math.max(Math.abs(max), 1) * 0.1;

  const x = (index: number) => (index / (points.length - 1)) * width;
  const y = (value: number) => HEIGHT - ((value - min + span * 0.08) / (span * 1.16)) * HEIGHT;

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(point.value).toFixed(2)}`)
    .join(" ");
  const area = `${line} L${width.toFixed(2)},${HEIGHT} L0,${HEIGHT} Z`;

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <View
      onLayout={onLayout}
      accessibilityLabel={`${label} over the last 24 hours, ${formatNumber(min, 2)} to ${formatNumber(max, 2)} ${unit}`}
    >
      <View style={styles.scale}>
        <Text style={styles.muted}>
          {formatNumber(max, 2)} {unit}
        </Text>
        <Text style={styles.muted}>
          {formatNumber(min, 2)} {unit}
        </Text>
      </View>

      {width > 0 ? (
        <Svg width={width} height={HEIGHT}>
          <Defs>
            <LinearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={color} stopOpacity={0.55} />
              <Stop offset="1" stopColor={color} stopOpacity={0.03} />
            </LinearGradient>
          </Defs>
          <Path d={area} fill="url(#trend-fill)" />
          <Path d={line} stroke={color} strokeWidth={2} fill="none" />
        </Svg>
      ) : (
        <View style={{ height: HEIGHT }} />
      )}

      <View style={styles.axis}>
        <Text style={styles.muted}>{first ? formatTimeOfDay(first.time) : ""}</Text>
        <Text style={styles.muted}>{last ? formatTimeOfDay(last.time) : ""}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  muted: { color: theme.color.textMuted, fontSize: 12 },
  scale: { flexDirection: "row", justifyContent: "space-between", marginBottom: 2 },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
});
