"""Loaders for the JSON activity/channel configuration in `backend/config`."""

from __future__ import annotations

import json
from functools import lru_cache

from lib.config import ACTIVITIES, CONFIG_DIR, Activity
from lib.models import ActivityThresholds, CrossSection


def normalize_site_number(site_id: str) -> str:
    """`USGS-02465000` and `02465000` both key the same configuration entry."""
    return site_id.split("-", 1)[-1].strip()


@lru_cache
def load_activity_thresholds() -> dict[tuple[str, Activity], ActivityThresholds]:
    payload = json.loads((CONFIG_DIR / "activity_thresholds.json").read_text(encoding="utf-8"))
    table: dict[tuple[str, Activity], ActivityThresholds] = {}
    for entry in payload["thresholds"]:
        site_number = normalize_site_number(entry["site_number"])
        for activity in ACTIVITIES:
            window = entry.get(activity)
            if not window:
                continue
            table[(site_number, activity)] = ActivityThresholds(
                activity=activity,
                parameter_code=window.get("parameter_code", "00060"),
                min_cfs=float(window["min_cfs"]),
                opt_min_cfs=float(window["opt_min_cfs"]),
                opt_max_cfs=float(window["opt_max_cfs"]),
                max_cfs=float(window["max_cfs"]),
                source="curated",
                note=window.get("note") or "Provisional window; tune with local knowledge",
            )
    return table


@lru_cache
def load_cross_sections() -> dict[str, CrossSection]:
    payload = json.loads((CONFIG_DIR / "cross_sections.json").read_text(encoding="utf-8"))
    return {
        normalize_site_number(entry["site_number"]): CrossSection(
            bottom_width_ft=float(entry["bottom_width_ft"]),
            side_slope=float(entry.get("side_slope", 2.0)),
            zero_flow_stage_ft=float(entry.get("zero_flow_stage_ft", 0.0)),
            manning_n=float(entry.get("manning_n", 0.035)),
            channel_slope=(
                float(entry["channel_slope"]) if entry.get("channel_slope") is not None else None
            ),
            source=entry.get("source", "configured"),
        )
        for entry in payload["cross_sections"]
    }


def thresholds_for(site_id: str, activity: Activity) -> ActivityThresholds | None:
    return load_activity_thresholds().get((normalize_site_number(site_id), activity))


def cross_section_for(site_id: str) -> CrossSection | None:
    return load_cross_sections().get(normalize_site_number(site_id))
