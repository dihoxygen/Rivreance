import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme";
import type { Activity } from "@shared/types";

const OPTIONS: { value: Activity; label: string; icon: string }[] = [
  { value: "kayaking", label: "Kayaking", icon: "🛶" },
  { value: "fishing", label: "Fishing", icon: "🎣" },
];

interface ActivityToggleProps {
  value: Activity;
  onChange: (activity: Activity) => void;
}

/** Optimal flows differ per sport, so the whole map re-colors when this changes. */
export function ActivityToggle({ value, onChange }: ActivityToggleProps) {
  return (
    <View style={styles.group} accessibilityRole="radiogroup" accessibilityLabel="Activity">
      {OPTIONS.map((option) => {
        const active = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(option.value)}
            style={[styles.option, active && styles.optionActive]}
          >
            <Text style={[styles.label, active && styles.labelActive]}>
              {option.icon} {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: "row",
    backgroundColor: theme.color.surface,
    borderColor: theme.color.border,
    borderWidth: 1,
    borderRadius: 999,
    padding: 3,
  },
  option: { paddingVertical: 7, paddingHorizontal: 14, borderRadius: 999 },
  optionActive: { backgroundColor: theme.color.accent },
  label: { color: theme.color.textMuted, fontSize: 13, fontWeight: "600" },
  labelActive: { color: "#04121c" },
});
