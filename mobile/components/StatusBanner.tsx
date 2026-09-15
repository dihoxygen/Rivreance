import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme";
import { formatAge, formatClock } from "@shared/format";
import type { HealthResponse } from "@shared/types";

interface StatusBannerProps {
  health: HealthResponse | undefined;
  isError: boolean;
  computedAt: string | null | undefined;
}

/**
 * Freshness is a safety property here: a paddler must never read a stale map as live.
 */
export function StatusBanner({ health, isError, computedAt }: StatusBannerProps) {
  const { text, warn } = describe(health, isError, computedAt);
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.banner, warn && styles.bannerWarn]}
    >
      <Text style={[styles.text, warn && styles.textWarn]} numberOfLines={2}>
        {text}
      </Text>
    </View>
  );
}

function describe(
  health: HealthResponse | undefined,
  isError: boolean,
  computedAt: string | null | undefined,
): { text: string; warn: boolean } {
  if (isError) {
    return { text: "Cannot reach the Rivreance API. Check the backend, then pull to refresh.", warn: true };
  }
  if (!health) {
    return { text: "Checking pipeline freshness…", warn: false };
  }
  if (health.last_run === null) {
    return { text: "No ingestion run yet — run the ETL pipeline.", warn: true };
  }
  if (health.stale || health.status !== "ok") {
    return {
      text: `Data may be stale — last successful update ${formatAge(health.last_run_age_minutes)}.`,
      warn: true,
    };
  }
  return {
    text: `Updated ${formatAge(health.last_run_age_minutes)}${
      computedAt ? ` · conditions computed ${formatClock(computedAt)}` : ""
    }`,
    warn: false,
  };
}

const styles = StyleSheet.create({
  banner: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 10,
    backgroundColor: theme.color.surface,
    borderWidth: 1,
    borderColor: theme.color.border,
  },
  bannerWarn: { backgroundColor: theme.color.warnSurface, borderColor: theme.color.warn },
  text: { color: theme.color.textMuted, fontSize: 12 },
  textWarn: { color: theme.color.warn },
});
