import type { Status, Trend, VelocityConfidence } from "./types";

export const STATUS_LABELS: Record<Status, string> = {
  green: "Optimal",
  yellow: "Caution",
  red: "Extreme",
  gray: "Unknown",
};

export const STATUS_COLORS: Record<Status, string> = {
  green: "#1a9850",
  yellow: "#f6c344",
  red: "#d73027",
  gray: "#9aa0a6",
};

export const STATUS_DESCRIPTIONS: Record<Status, string> = {
  green: "Flow is inside the optimal window for this activity",
  yellow: "Runnable but sub-optimal — low or pushy",
  red: "Too low to float or too high to be safe",
  gray: "No fresh reading, or no gage on this reach",
};

export const TREND_LABELS: Record<Trend, string> = {
  rising: "Rising",
  falling: "Falling",
  steady: "Steady",
  unknown: "Unknown",
};

export const TREND_ICONS: Record<Trend, string> = {
  rising: "▲",
  falling: "▼",
  steady: "▬",
  unknown: "?",
};

export const VELOCITY_METHOD_LABELS: Record<string, string> = {
  field_rating: "Field velocity rating",
  field_area_rating: "Field area rating (Q/A)",
  cross_section: "Trapezoidal cross-section (Q/A)",
  manning: "Manning's equation",
  nhdplus_erom: "NHDPlus reach estimate",
};

export const CONFIDENCE_LABELS: Record<VelocityConfidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatOrdinal(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Math.round(value);
  const suffix =
    rounded % 100 >= 11 && rounded % 100 <= 13
      ? "th"
      : (["th", "st", "nd", "rd"][rounded % 10] ?? "th");
  return `${rounded}${suffix}`;
}

export function formatFlow(cfs: number | null | undefined): string {
  if (cfs === null || cfs === undefined) return "—";
  return `${cfs.toLocaleString(undefined, { maximumFractionDigits: cfs < 100 ? 1 : 0 })} cfs`;
}

export function formatAge(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "unknown age";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours.toFixed(hours < 10 ? 1 : 0)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function formatClock(isoTime: string | null | undefined): string {
  if (!isoTime) return "—";
  return new Date(isoTime).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatTimeOfDay(isoTime: string): string {
  return new Date(isoTime).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Position of a flow value inside its activity window, clamped to 0-100 %. */
export function thresholdPosition(
  value: number,
  min: number,
  max: number,
): number {
  if (max <= min) return 50;
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
}
