from __future__ import annotations

import math

import pytest

from lib.models import CrossSection, PowerLawRating
from lib.velocity import (
    FPS_TO_MPH,
    estimate_velocity,
    hydraulic_radius_ft,
    trapezoid_area_sqft,
    velocity_from_cross_section,
    velocity_from_erom,
    velocity_from_manning,
    velocity_from_velocity_rating,
)


def test_trapezoid_area_matches_hand_calculation():
    # W*d + m*d^2 = 50*4 + 2*16
    assert trapezoid_area_sqft(4.0, 50.0, 2.0) == pytest.approx(232.0)


def test_trapezoid_area_is_zero_for_dry_channel():
    assert trapezoid_area_sqft(-1.0, 50.0, 2.0) == 0.0
    assert trapezoid_area_sqft(0.0, 50.0, 2.0) == 0.0


def test_hydraulic_radius_is_area_over_wetted_perimeter():
    area = trapezoid_area_sqft(4.0, 50.0, 2.0)
    perimeter = 50.0 + 2 * 4.0 * math.sqrt(5)
    assert hydraulic_radius_ft(4.0, 50.0, 2.0) == pytest.approx(area / perimeter)


def test_velocity_from_cross_section_uses_flow_depth_not_gage_height():
    cross_section = CrossSection(bottom_width_ft=50.0, side_slope=2.0, zero_flow_stage_ft=1.0)
    estimate = velocity_from_cross_section(464.0, gage_height_ft=5.0, cross_section=cross_section)

    assert estimate is not None
    assert estimate.area_sqft == pytest.approx(232.0)  # depth = 5 - 1 = 4 ft
    assert estimate.velocity_fps == pytest.approx(2.0)
    assert estimate.velocity_mph == pytest.approx(2.0 * FPS_TO_MPH)
    assert estimate.method == "cross_section"


def test_velocity_from_cross_section_returns_none_when_channel_is_dry():
    cross_section = CrossSection(bottom_width_ft=50.0, zero_flow_stage_ft=6.0)
    assert velocity_from_cross_section(100.0, 5.0, cross_section) is None


def test_manning_velocity_matches_formula():
    cross_section = CrossSection(
        bottom_width_ft=50.0, side_slope=2.0, zero_flow_stage_ft=0.0, manning_n=0.035,
        channel_slope=0.001,
    )
    estimate = velocity_from_manning(4.0, cross_section)

    assert estimate is not None
    radius = hydraulic_radius_ft(4.0, 50.0, 2.0)
    expected = 1.486 / 0.035 * radius ** (2 / 3) * math.sqrt(0.001)
    assert estimate.velocity_fps == pytest.approx(expected)
    assert estimate.confidence == "low"


def test_manning_requires_a_slope():
    assert velocity_from_manning(4.0, CrossSection(bottom_width_ft=50.0)) is None


def test_velocity_rating_is_used_inside_its_measured_range():
    rating = PowerLawRating(k=0.2, exponent=0.4, count=12, r_squared=0.9, q_min=10, q_max=500)
    estimate = velocity_from_velocity_rating(100.0, rating)

    assert estimate is not None
    assert estimate.velocity_fps == pytest.approx(0.2 * 100**0.4)
    assert estimate.confidence == "high"
    assert estimate.area_sqft == pytest.approx(100.0 / estimate.velocity_fps)


def test_velocity_rating_confidence_drops_when_extrapolating():
    rating = PowerLawRating(k=0.2, exponent=0.4, count=12, r_squared=0.9, q_min=10, q_max=500)
    estimate = velocity_from_velocity_rating(800.0, rating)

    assert estimate is not None
    assert estimate.confidence == "medium"
    assert "outside the measured range" in (estimate.note or "")


@pytest.mark.parametrize(
    ("discharge", "rating"),
    [
        (5000.0, PowerLawRating(k=0.2, exponent=0.4, count=12, r_squared=0.9, q_min=10, q_max=500)),
        (100.0, PowerLawRating(k=0.2, exponent=0.4, count=12, r_squared=0.2, q_min=10, q_max=500)),
        (100.0, PowerLawRating(k=0.2, exponent=0.4, count=2, r_squared=0.99, q_min=10, q_max=500)),
    ],
)
def test_velocity_rating_is_rejected_when_untrustworthy(discharge, rating):
    assert velocity_from_velocity_rating(discharge, rating) is None


def test_erom_scaling_returns_mean_annual_velocity_at_mean_annual_flow():
    estimate = velocity_from_erom(90.0, erom_flow_cfs=90.0, erom_velocity_fps=1.2)
    assert estimate is not None
    assert estimate.velocity_fps == pytest.approx(1.2)
    assert estimate.confidence == "low"


def test_erom_scaling_increases_with_discharge():
    low = velocity_from_erom(45.0, 90.0, 1.2)
    high = velocity_from_erom(900.0, 90.0, 1.2)
    assert low is not None and high is not None
    assert low.velocity_fps < 1.2 < high.velocity_fps


def test_estimate_velocity_prefers_field_rating_over_cross_section():
    rating = PowerLawRating(k=0.3, exponent=0.4, count=10, r_squared=0.8, q_min=10, q_max=500)
    estimate = estimate_velocity(
        discharge_cfs=100.0,
        gage_height_ft=5.0,
        velocity_rating=rating,
        cross_section=CrossSection(bottom_width_ft=50.0, zero_flow_stage_ft=1.0),
    )
    assert estimate is not None
    assert estimate.method == "field_rating"


def test_estimate_velocity_falls_back_through_the_method_chain():
    cross_section = CrossSection(bottom_width_ft=50.0, side_slope=2.0, zero_flow_stage_ft=1.0)
    unusable = PowerLawRating(k=0.3, exponent=0.4, count=2, r_squared=0.1, q_min=10, q_max=20)

    assert (
        estimate_velocity(
            discharge_cfs=100.0,
            gage_height_ft=5.0,
            velocity_rating=unusable,
            cross_section=cross_section,
        ).method
        == "cross_section"
    )
    assert (
        estimate_velocity(
            discharge_cfs=100.0, erom_flow_cfs=90.0, erom_velocity_fps=1.2
        ).method
        == "nhdplus_erom"
    )
    # Stage only: Manning is the sole option.
    stage_only = CrossSection(bottom_width_ft=50.0, zero_flow_stage_ft=1.0, channel_slope=0.001)
    stage_estimate = estimate_velocity(
        discharge_cfs=None, gage_height_ft=5.0, cross_section=stage_only
    )
    assert stage_estimate is not None and stage_estimate.method == "manning"


def test_estimate_velocity_returns_none_without_usable_inputs():
    assert estimate_velocity(discharge_cfs=None) is None
    assert estimate_velocity(discharge_cfs=0.0, gage_height_ft=None) is None
