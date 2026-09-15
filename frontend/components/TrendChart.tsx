"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber, formatTimeOfDay } from "@shared/format";
import type { SeriesPoint } from "@shared/types";

interface TrendChartProps {
  points: SeriesPoint[];
  unit: string;
  color: string;
  label: string;
}

export function TrendChart({ points, unit, color, label }: TrendChartProps) {
  if (points.length < 2) {
    return <p className="muted small">Not enough recent readings to chart.</p>;
  }

  const data = points.map((point) => ({
    time: point.time,
    value: point.value,
    clock: formatTimeOfDay(point.time),
  }));

  return (
    <div className="chart" aria-label={`${label} over the last 24 hours`}>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.55} />
              <stop offset="100%" stopColor={color} stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.16)" vertical={false} />
          <XAxis
            dataKey="clock"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            minTickGap={48}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            width={44}
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid rgba(148,163,184,0.3)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#e2e8f0" }}
            formatter={(value: number) => [`${formatNumber(value, 2)} ${unit}`, label]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill="url(#trend-fill)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
