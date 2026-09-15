"use client";

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
  if (isError) {
    return (
      <div className="banner banner--warn" role="status">
        Cannot reach the Rivreance API. Start the backend, then reload.
      </div>
    );
  }
  if (!health) {
    return (
      <div className="banner" role="status">
        Checking pipeline freshness…
      </div>
    );
  }
  if (health.last_run === null) {
    return (
      <div className="banner banner--warn" role="status">
        No ingestion run yet — run <code>python -m etl.run_pipeline --with-flowlines</code>.
      </div>
    );
  }
  if (health.stale || health.status !== "ok") {
    return (
      <div className="banner banner--warn" role="status">
        Data may be stale — last successful update {formatAge(health.last_run_age_minutes)}.
      </div>
    );
  }
  return (
    <div className="banner" role="status">
      Updated {formatAge(health.last_run_age_minutes)}
      {computedAt ? ` · conditions computed ${formatClock(computedAt)}` : ""}
    </div>
  );
}
