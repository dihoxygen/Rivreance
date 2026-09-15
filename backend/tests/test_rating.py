from __future__ import annotations

import pytest

from lib.rating import fit_power_law, fit_station_rating


def test_fit_power_law_recovers_known_coefficients():
    k, exponent = 0.35, 0.42
    pairs = [(discharge, k * discharge**exponent) for discharge in (5, 20, 80, 320, 1280)]

    rating = fit_power_law(pairs)

    assert rating is not None
    assert rating.k == pytest.approx(k, rel=1e-6)
    assert rating.exponent == pytest.approx(exponent, rel=1e-6)
    assert rating.r_squared == pytest.approx(1.0, abs=1e-9)
    assert (rating.q_min, rating.q_max) == (5, 1280)
    assert rating.count == 5


def test_fit_power_law_needs_enough_spread_and_points():
    assert fit_power_law([(10, 1), (20, 2), (30, 3)]) is None  # too few points
    assert fit_power_law([(10, 1), (10, 1.1), (10, 0.9), (10, 1.2)]) is None  # no discharge spread
    assert fit_power_law([(10, 0), (20, -1), (30, 2), (40, 3)]) is None  # non-positive dropped


def test_fit_power_law_reports_scatter_in_r_squared():
    noisy = [(10, 1.0), (100, 1.2), (1000, 0.9), (5000, 1.4), (20, 3.0)]
    rating = fit_power_law(noisy)
    assert rating is not None
    assert rating.r_squared < 0.5


def _measurement(time: str, flow: str, area=None, width=None, velocity=None, velocity_unit="ft/s"):
    return {
        "properties": {
            "time": time,
            "channel_flow": flow,
            "channel_area": area,
            "channel_width": width,
            "channel_velocity": velocity,
            "channel_velocity_unit": velocity_unit,
            "channel_area_unit": "ft^2",
            "channel_width_unit": "ft",
        }
    }


def test_fit_station_rating_from_usgs_shaped_features():
    measurements = [
        _measurement("2026-08-10T16:47:43+00:00", "28.8", "40.6", "50.0", "0.71"),
        _measurement("2026-07-01T19:11:23+00:00", "16.3", "17.6", "38.0", "0.93"),
        _measurement("2026-04-24T16:03:17+00:00", "12.3", "17.1", "40.0", "0.72"),
        _measurement("2026-02-11T15:00:00+00:00", "120.0", "98.0", "55.0", "1.22"),
        _measurement("2025-11-05T15:00:00+00:00", "60.0", "62.0", "52.0", "0.97"),
    ]

    rating = fit_station_rating("USGS-02461192", measurements)

    assert rating.measurement_count == 5
    assert rating.velocity_rating is not None
    assert rating.velocity_rating.exponent > 0  # velocity rises with discharge
    assert rating.area_rating is not None
    assert rating.median_width_ft == pytest.approx(50.0)
    assert rating.fitted_at is not None


def test_fit_station_rating_skips_zero_flow_and_stale_visits():
    measurements = [
        _measurement("1967-10-25T05:00:00+00:00", "0.00"),
        _measurement("1952-12-10T06:00:00+00:00", "4120", velocity="2.0"),
        _measurement("2026-08-10T16:47:43+00:00", "28.8", velocity="0.71"),
    ]

    rating = fit_station_rating("USGS-02462500", measurements, max_age_years=15.0)

    assert rating.measurement_count == 1
    assert rating.velocity_rating is None


def test_fit_station_rating_normalizes_metric_velocity_units():
    metric = [0.3, 0.45, 0.62, 0.8]
    discharges = ["10", "20", "40", "80"]
    times = [f"2026-0{month}-10T00:00:00+00:00" for month in (5, 6, 7, 8)]

    metric_rating = fit_station_rating(
        "USGS-TEST",
        [
            _measurement(time, flow, velocity=str(value), velocity_unit="m/s")
            for time, flow, value in zip(times, discharges, metric, strict=True)
        ],
    )
    imperial_rating = fit_station_rating(
        "USGS-TEST",
        [
            _measurement(time, flow, velocity=str(value * 3.28084), velocity_unit="ft/s")
            for time, flow, value in zip(times, discharges, metric, strict=True)
        ],
    )

    assert metric_rating.velocity_rating is not None
    assert imperial_rating.velocity_rating is not None
    assert metric_rating.velocity_rating.k == pytest.approx(imperial_rating.velocity_rating.k)
    assert metric_rating.velocity_rating.exponent == pytest.approx(
        imperial_rating.velocity_rating.exponent
    )
