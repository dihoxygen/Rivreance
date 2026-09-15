"use client";

import type { Activity } from "@/lib/types";

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
    <div className="segmented" role="radiogroup" aria-label="Activity">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          className={value === option.value ? "is-active" : ""}
          onClick={() => onChange(option.value)}
        >
          <span aria-hidden>{option.icon}</span>
          {option.label}
        </button>
      ))}
    </div>
  );
}
