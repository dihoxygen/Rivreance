"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ActivityToggle } from "@/components/ActivityToggle";
import { Legend } from "@/components/Legend";
import { RiverMap } from "@/components/RiverMap";
import { SitePopup } from "@/components/SitePopup";
import { StatusBanner } from "@/components/StatusBanner";
import { api, queryKeys } from "@/lib/api";
import { STATUS_COLORS, STATUS_LABELS } from "@/lib/format";
import type { Activity, Status } from "@/lib/types";

const STATUS_ORDER: Status[] = ["green", "yellow", "red", "gray"];

export default function MapPage() {
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
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden>
            ~
          </span>
          <div>
            <h1>Rivreance</h1>
            <p className="muted small">
              {basin ? `${basin.name} · HUC ${basin.huc8}` : "Loading basins…"}
            </p>
          </div>
        </div>

        <div className="topbar__controls">
          <ActivityToggle value={activity} onChange={setActivity} />
          {basins.data && basins.data.length > 1 ? (
            <label className="field">
              <span className="muted small">Basin</span>
              <select
                value={basinIndex}
                onChange={(event) => {
                  setBasinIndex(Number(event.target.value));
                  setSelectedSiteId(null);
                }}
              >
                {basins.data.map((option, index) => (
                  <option key={option.huc8} value={index}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <StatusBanner
          health={health.data}
          isError={health.isError}
          computedAt={segments.data?.computed_at}
        />
      </header>

      <div className="content">
        {basin ? (
          <RiverMap
            basin={basin}
            segments={segments.data}
            sites={sites.data}
            selectedSiteId={selectedSiteId}
            onSelectSite={setSelectedSiteId}
          />
        ) : (
          <div className="map-placeholder">
            {basins.isError ? "Could not load basins from the API." : "Loading map…"}
          </div>
        )}

        <div className="overlays">
          <section className="gage-summary" aria-label="Gage status summary">
            <h2 className="small">
              {sites.data?.features.length ?? 0} gages ·{" "}
              {activity === "kayaking" ? "paddling" : "fishing"} thresholds
            </h2>
            <ul>
              {STATUS_ORDER.filter((status) => gageCounts[status]).map((status) => (
                <li key={status}>
                  <i style={{ background: STATUS_COLORS[status] }} aria-hidden />
                  {gageCounts[status]} {STATUS_LABELS[status].toLowerCase()}
                </li>
              ))}
            </ul>
            {segments.isPending || sites.isPending ? (
              <p className="muted small">Loading conditions…</p>
            ) : null}
          </section>

          <Legend statusCounts={segments.data?.status_counts ?? {}} />
        </div>

        {selectedSite ? (
          <SitePopup site={selectedSite} onClose={() => setSelectedSiteId(null)} />
        ) : null}
      </div>
    </main>
  );
}
