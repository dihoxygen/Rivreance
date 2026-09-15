/** Mirrors the CSS custom properties in `frontend/app/globals.css`. */
export const theme = {
  color: {
    bg: "#0b1015",
    bgElevated: "#0f1722",
    surface: "rgba(255, 255, 255, 0.05)",
    border: "rgba(148, 163, 184, 0.22)",
    text: "#e8eef5",
    textMuted: "#93a1b4",
    accent: "#38bdf8",
    warn: "#facc15",
    warnSurface: "rgba(250, 204, 21, 0.12)",
  },
  radius: 14,
  space: (steps: number) => steps * 4,
} as const;
