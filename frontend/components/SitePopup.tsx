"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState } from "react";

import { api, queryKeys, REFRESH_INTERVAL_MS } from "@/lib/api";
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

/** Recharts is heavy; keep it out of the initial bundle. */
const LazyTrendChart = dynamic(
  () => import("./TrendChart").then((module) => module.TrendChart),
  { ssr: false, loading: () => <p className="muted small">Loading chart…</p> },
);

interface SitePopupProps {
  site: SiteProperties;
  onClose: () => void;
}

export function SitePopup({ site, onClose }: SitePopupProps) {
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
    <aside className="site-panel" aria-label={`Conditions at ${site.name}`}>
      <header className="site-panel__header">
        <div>
          <span className="status-pill" style={{ background: STATUS_COLORS[site.status] }}>
            {STATUS_LABELS[site.status]}
          </span>
          <h2>{site.name}</h2>
          <p className="muted small">
            USGS {site.site_number}
            {site.drainage_area_sqmi
              ? ` · ${formatNumber(site.drainage_area_sqmi, 0)} sq mi drainage`
              : ""}
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </header>

      <p className="reason">{site.reason}</p>

      <dl className="metrics">
        <Metric label="Discharge" value={formatFlow(site.discharge_cfs)} />
        <Metric
          label="Gage height"
          value={site.gage_height_ft === null ? "—" : `${formatNumber(site.gage_height_ft, 2)} ft`}
        />
        <Metric
          label="Velocity"
          value={
            site.velocity_mph === null
              ? "—"
              : `${formatNumber(site.velocity_mph, 2)} mph`
          }
          hint={site.velocity_fps === null ? undefined : `${formatNumber(site.velocity_fps, 2)} fps`}
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
        <Metric label="Reading age" value={formatAge(site.age_minutes)} hint={formatClock(site.observed_at)} />
      </dl>

      {site.thresholds && site.discharge_cfs !== null ? (
        <ThresholdBar thresholds={site.thresholds} value={site.discharge_cfs} />
      ) : null}

      {site.velocity_method ? (
        <section className="panel-section">
          <h3>How velocity was estimated</h3>
          <p className="small">
            <strong>{VELOCITY_METHOD_LABELS[site.velocity_method] ?? site.velocity_method}</strong>
            {site.velocity_confidence ? ` · ${CONFIDENCE_LABELS[site.velocity_confidence]}` : ""}
          </p>
          {site.velocity_note ? <p className="muted small">{site.velocity_note}</p> : null}
          {site.cross_section_area_sqft ? (
            <p className="muted small">
              Implied cross-sectional area {formatNumber(site.cross_section_area_sqft, 0)} ft²
            </p>
          ) : null}
        </section>
      ) : null}

      {parameters.length > 0 ? (
        <section className="panel-section">
          <div className="panel-section__head">
            <h3>Last 24 hours</h3>
            {parameters.length > 1 ? (
              <div className="mini-toggle" role="group" aria-label="Chart parameter">
                {parameters.map((code) => (
                  <button
                    key={code}
                    type="button"
                    className={code === activeParameter ? "is-active" : ""}
                    onClick={() => setParameter(code)}
                  >
                    {PARAMETER_LABELS[code]?.label ?? code}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          {series.isPending ? <p className="muted small">Loading readings…</p> : null}
          {series.isError ? <p className="muted small">No cached readings for this parameter.</p> : null}
          {series.data ? (
            <LazyTrendChart
              points={series.data.points}
              unit={series.data.unit || parameterMeta.unit}
              color={STATUS_COLORS[site.status]}
              label={parameterMeta.label}
            />
          ) : null}
        </section>
      ) : null}

      <a
        className="external-link"
        href={`https://waterdata.usgs.gov/monitoring-location/${site.site_number}/`}
        target="_blank"
        rel="noreferrer"
      >
        Open the USGS station page →
      </a>
    </aside>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric">
      <dt>{label}</dt>
      <dd>
        {value}
        {hint ? <span className="muted small"> {hint}</span> : null}
      </dd>
    </div>
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
  const share = (from: number, to: number) => `${((to - from) / domainMax) * 100}%`;
  const markerLeft = `${Math.min(100, Math.max(0, (value / domainMax) * 100))}%`;

  return (
    <section className="panel-section">
      <div className="panel-section__head">
        <h3>{thresholds.activity === "kayaking" ? "Paddling" : "Fishing"} flow window</h3>
        <span className="muted small">{thresholds.source.replace(/_/g, " ")}</span>
      </div>
      <div className="threshold-bar" role="img" aria-label="Flow window with current reading">
        <span style={{ width: share(0, thresholds.min_cfs), background: STATUS_COLORS.red }} />
        <span
          style={{
            width: share(thresholds.min_cfs, thresholds.opt_min_cfs),
            background: STATUS_COLORS.yellow,
          }}
        />
        <span
          style={{
            width: share(thresholds.opt_min_cfs, thresholds.opt_max_cfs),
            background: STATUS_COLORS.green,
          }}
        />
        <span
          style={{
            width: share(thresholds.opt_max_cfs, thresholds.max_cfs),
            background: STATUS_COLORS.yellow,
          }}
        />
        <span
          style={{ width: share(thresholds.max_cfs, domainMax), background: STATUS_COLORS.red }}
        />
        <i className="threshold-bar__marker" style={{ left: markerLeft }} aria-hidden />
      </div>
      <div className="threshold-scale small muted">
        <span>{formatFlow(thresholds.min_cfs)} min</span>
        <span>
          {formatFlow(thresholds.opt_min_cfs)}–{formatFlow(thresholds.opt_max_cfs)} optimal
        </span>
        <span>{formatFlow(thresholds.max_cfs)} max</span>
      </div>
      {thresholds.note ? <p className="muted small">{thresholds.note}</p> : null}
    </section>
  );
}
