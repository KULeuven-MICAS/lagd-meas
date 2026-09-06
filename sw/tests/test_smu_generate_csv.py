import csv

import pytest

from sw.tests.smu_calibrate import find_transition_interval, validate_calibration_range
from sw.tests.smu_generate_csv import get_calibration_field_order, load_calibration_values


def test_get_calibration_field_order():
    assert get_calibration_field_order(False) == [
        "base",
        "j",
        "hup_sf1",
        "hdn_sf1",
    ]
    assert get_calibration_field_order(True)[:6] == [
        "base",
        "j",
        "hup_sf1",
        "hdn_sf1",
        "hup_sf2",
        "hdn_sf2",
    ]
    assert get_calibration_field_order(True)[-2:] == ["hup_sf31", "hdn_sf31"]


def test_load_calibration_values_resumes_from_last_known_value(tmp_path):
    csv_path = tmp_path / "currents.csv"
    fieldnames = ["base", "j", "hup_sf1", "hdn_sf1", "hup_sf2", "hdn_sf2"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "base": "6.4e-05",
            "j": "-180.5e-6",
            "hup_sf1": "-1e-6",
            "hdn_sf1": "1e-6",
        })

    values = load_calibration_values(csv_path, fieldnames)
    assert values == {
        "base": "6.4e-05",
        "j": "-180.5e-6",
        "hup_sf1": "-1e-6",
        "hdn_sf1": "1e-6",
        "hup_sf2": "",
        "hdn_sf2": "",
    }


def test_validate_calibration_range_uses_smu_limit_for_all_scaling_factors():
    for mode in ["hup", "hdn"]:
        for sf in range(1, 32):
            min_current = -5e-6 if mode == "hup" else 5e-6
            max_current = -5e-5 if mode == "hup" else 5e-5
            scaled_min, scaled_max = validate_calibration_range(mode, min_current, max_current, sf)
            assert scaled_min <= 0.002
            assert scaled_max <= 0.002

    with pytest.raises(ValueError, match="exceeds B2901BL limit"):
        validate_calibration_range("hup", -1e-3, -2e-3, 2)


def test_find_transition_interval_reduces_the_search_window():
    def linear_response(x):
        return x

    lo, hi = find_transition_interval(0.0, 1.0, linear_response, threshold=0.5, broad_points=8)
    assert lo < 0.5 < hi
    assert hi - lo < 0.5
