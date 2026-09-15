r"""Velocity estimation.

USGS gages publish discharge (:math:`Q`, cfs) and gage height (:math:`h`, ft) but
almost never mean velocity, so Rivreance estimates it. Four methods are tried in
order of trustworthiness:

1. **Field velocity rating** — power law :math:`v = k Q^{m}` fitted from that
   station's own discrete channel measurements.
2. **Field area rating** — power law :math:`A = k Q^{m}` from the same
   measurements, then :math:`v = Q / A`.
3. **Configured cross-section** — trapezoidal channel from `cross_sections.json`
   gives :math:`A(h)`, then :math:`v = Q / A`.
4. **Manning's equation** — :math:`v = \frac{1.486}{n} R^{2/3} S^{1/2}`; the only
   option when discharge is missing but stage is available.
5. **NHDPlus EROM fallback** — scale the reach's mean-annual velocity by
   :math:`(Q / Q_{ma})^{0.4}` (at-a-station hydraulic geometry).
"""

from __future__ import annotations

import math

from lib.models import CrossSection, PowerLawRating, VelocityEstimate

FPS_TO_MPH = 3600.0 / 5280.0
#: Manning coefficient in US customary units (1.486 = 1.0 m^(1/3)/s converted).
MANNING_UNIT_FACTOR = 1.486
#: At-a-station velocity/discharge exponent (Leopold & Maddock).
EROM_SCALING_EXPONENT = 0.4
#: Ratings extrapolated beyond this multiple of their fitted range lose confidence.
EXTRAPOLATION_TOLERANCE = 2.0
MIN_RATING_R_SQUARED = 0.5


def mph(velocity_fps: float) -> float:
    return velocity_fps * FPS_TO_MPH


def trapezoid_area_sqft(depth_ft: float, bottom_width_ft: float, side_slope: float) -> float:
    """Wetted area of a trapezoidal channel: ``W*d + m*d^2``."""
    if depth_ft <= 0 or bottom_width_ft <= 0:
        return 0.0
    return bottom_width_ft * depth_ft + side_slope * depth_ft**2


def trapezoid_wetted_perimeter_ft(
    depth_ft: float, bottom_width_ft: float, side_slope: float
) -> float:
    if depth_ft <= 0 or bottom_width_ft <= 0:
        return 0.0
    return bottom_width_ft + 2.0 * depth_ft * math.sqrt(1.0 + side_slope**2)


def hydraulic_radius_ft(depth_ft: float, bottom_width_ft: float, side_slope: float) -> float:
    perimeter = trapezoid_wetted_perimeter_ft(depth_ft, bottom_width_ft, side_slope)
    if perimeter <= 0:
        return 0.0
    return trapezoid_area_sqft(depth_ft, bottom_width_ft, side_slope) / perimeter


def flow_depth_ft(gage_height_ft: float, cross_section: CrossSection) -> float:
    """Convert gage height to flow depth using the station's stage of zero flow."""
    return gage_height_ft - cross_section.zero_flow_stage_ft


def evaluate_power_law(rating: PowerLawRating, discharge_cfs: float) -> float:
    return rating.k * discharge_cfs**rating.exponent


def _rating_confidence(rating: PowerLawRating, discharge_cfs: float) -> str | None:
    """`None` means the rating should not be used at this discharge."""
    if rating.count < 4 or rating.r_squared < MIN_RATING_R_SQUARED:
        return None
    low = rating.q_min / EXTRAPOLATION_TOLERANCE
    high = rating.q_max * EXTRAPOLATION_TOLERANCE
    if not low <= discharge_cfs <= high:
        return None
    if rating.q_min <= discharge_cfs <= rating.q_max:
        return "high"
    return "medium"


def velocity_from_velocity_rating(
    discharge_cfs: float, rating: PowerLawRating
) -> VelocityEstimate | None:
    if discharge_cfs <= 0:
        return None
    confidence = _rating_confidence(rating, discharge_cfs)
    if confidence is None:
        return None
    velocity_fps = evaluate_power_law(rating, discharge_cfs)
    if velocity_fps <= 0:
        return None
    note = (
        f"v = {rating.k:.3g}*Q^{rating.exponent:.3g} fitted to "
        f"{rating.count} USGS field measurements (R²={rating.r_squared:.2f})"
    )
    if confidence == "medium":
        note += "; discharge is outside the measured range"
    return VelocityEstimate(
        velocity_fps=velocity_fps,
        velocity_mph=mph(velocity_fps),
        method="field_rating",
        confidence=confidence,  # type: ignore[arg-type]
        area_sqft=discharge_cfs / velocity_fps,
        note=note,
    )


def velocity_from_area_rating(
    discharge_cfs: float, rating: PowerLawRating
) -> VelocityEstimate | None:
    if discharge_cfs <= 0:
        return None
    confidence = _rating_confidence(rating, discharge_cfs)
    if confidence is None:
        return None
    area_sqft = evaluate_power_law(rating, discharge_cfs)
    if area_sqft <= 0:
        return None
    velocity_fps = discharge_cfs / area_sqft
    return VelocityEstimate(
        velocity_fps=velocity_fps,
        velocity_mph=mph(velocity_fps),
        method="field_area_rating",
        confidence="medium" if confidence == "high" else "low",
        area_sqft=area_sqft,
        note=(
            f"v = Q/A with A = {rating.k:.3g}*Q^{rating.exponent:.3g} from "
            f"{rating.count} field measurements (R²={rating.r_squared:.2f})"
        ),
    )


def velocity_from_cross_section(
    discharge_cfs: float, gage_height_ft: float, cross_section: CrossSection
) -> VelocityEstimate | None:
    """``v = Q / A`` with A from the configured trapezoidal profile."""
    depth = flow_depth_ft(gage_height_ft, cross_section)
    area = trapezoid_area_sqft(depth, cross_section.bottom_width_ft, cross_section.side_slope)
    if discharge_cfs <= 0 or area <= 0:
        return None
    return VelocityEstimate(
        velocity_fps=discharge_cfs / area,
        velocity_mph=mph(discharge_cfs / area),
        method="cross_section",
        confidence="medium",
        area_sqft=area,
        hydraulic_radius_ft=hydraulic_radius_ft(
            depth, cross_section.bottom_width_ft, cross_section.side_slope
        ),
        note=(
            f"v = Q/A with trapezoidal A={area:.0f} ft² at {depth:.2f} ft depth "
            f"(W={cross_section.bottom_width_ft:.0f} ft, m={cross_section.side_slope:g})"
        ),
    )


def velocity_from_manning(
    gage_height_ft: float, cross_section: CrossSection
) -> VelocityEstimate | None:
    """Manning's equation; needs a channel slope and roughness."""
    slope = cross_section.channel_slope
    if slope is None or slope <= 0:
        return None
    depth = flow_depth_ft(gage_height_ft, cross_section)
    radius = hydraulic_radius_ft(depth, cross_section.bottom_width_ft, cross_section.side_slope)
    if radius <= 0 or cross_section.manning_n <= 0:
        return None
    velocity_fps = (
        MANNING_UNIT_FACTOR / cross_section.manning_n * radius ** (2 / 3) * math.sqrt(slope)
    )
    return VelocityEstimate(
        velocity_fps=velocity_fps,
        velocity_mph=mph(velocity_fps),
        method="manning",
        confidence="low",
        area_sqft=trapezoid_area_sqft(
            depth, cross_section.bottom_width_ft, cross_section.side_slope
        ),
        hydraulic_radius_ft=radius,
        note=(
            f"Manning v = 1.486/n · R^(2/3) · S^(1/2) with n={cross_section.manning_n:g}, "
            f"R={radius:.2f} ft, S={slope:g}"
        ),
    )


def velocity_from_erom(
    discharge_cfs: float, erom_flow_cfs: float, erom_velocity_fps: float
) -> VelocityEstimate | None:
    """Scale the NHDPlus mean-annual velocity to the observed discharge."""
    if discharge_cfs <= 0 or erom_flow_cfs <= 0 or erom_velocity_fps <= 0:
        return None
    velocity_fps = erom_velocity_fps * (discharge_cfs / erom_flow_cfs) ** EROM_SCALING_EXPONENT
    return VelocityEstimate(
        velocity_fps=velocity_fps,
        velocity_mph=mph(velocity_fps),
        method="nhdplus_erom",
        confidence="low",
        area_sqft=discharge_cfs / velocity_fps,
        note=(
            f"NHDPlus mean-annual v={erom_velocity_fps:.2f} fps at Q={erom_flow_cfs:.0f} cfs "
            f"scaled by (Q/Qma)^{EROM_SCALING_EXPONENT}"
        ),
    )


def estimate_velocity(
    *,
    discharge_cfs: float | None,
    gage_height_ft: float | None = None,
    velocity_rating: PowerLawRating | None = None,
    area_rating: PowerLawRating | None = None,
    cross_section: CrossSection | None = None,
    erom_flow_cfs: float | None = None,
    erom_velocity_fps: float | None = None,
) -> VelocityEstimate | None:
    """Best available velocity estimate, or `None` when nothing can be computed."""
    if discharge_cfs is not None and discharge_cfs > 0:
        if velocity_rating is not None:
            estimate = velocity_from_velocity_rating(discharge_cfs, velocity_rating)
            if estimate is not None:
                return estimate
        if area_rating is not None:
            estimate = velocity_from_area_rating(discharge_cfs, area_rating)
            if estimate is not None:
                return estimate
        if cross_section is not None and gage_height_ft is not None:
            estimate = velocity_from_cross_section(discharge_cfs, gage_height_ft, cross_section)
            if estimate is not None:
                return estimate
        if erom_flow_cfs is not None and erom_velocity_fps is not None:
            estimate = velocity_from_erom(discharge_cfs, erom_flow_cfs, erom_velocity_fps)
            if estimate is not None:
                return estimate
    if cross_section is not None and gage_height_ft is not None:
        return velocity_from_manning(gage_height_ft, cross_section)
    return None
