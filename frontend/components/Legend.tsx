"use client";

import { useState } from "react";

import { STATUS_COLORS, STATUS_DESCRIPTIONS, STATUS_LABELS } from "@shared/format";
import { MAP_ATTRIBUTION_NOTE } from "@/lib/mapStyle";
import type { Status } from "@shared/types";

const ORDER: Status[] = ["green", "yellow", "red", "gray"];

interface LegendProps {
  statusCounts: Partial<Record<Status, number>>;
}

export function Legend({ statusCounts }: LegendProps) {
  const [open, setOpen] = useState(true);

  return (
    <section className={`legend ${open ? "" : "legend--collapsed"}`} aria-label="Map legend">
      <button
        type="button"
        className="legend__toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        Legend
        <span aria-hidden>{open ? "▾" : "▴"}</span>
      </button>
      {open ? (
        <>
          <ul>
            {ORDER.map((status) => (
              <li key={status}>
                <i style={{ background: STATUS_COLORS[status] }} aria-hidden />
                <span>
                  <strong>{STATUS_LABELS[status]}</strong>
                  {statusCounts[status] ? ` · ${statusCounts[status]} reaches` : ""}
                  <br />
                  <span className="muted small">{STATUS_DESCRIPTIONS[status]}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="muted small legend__note">
            Reaches take the status of the gage on their mainstem, or of a gage within 5 km.
            Estimates are not safety advice. {MAP_ATTRIBUTION_NOTE}.
          </p>
        </>
      ) : null}
    </section>
  );
}
