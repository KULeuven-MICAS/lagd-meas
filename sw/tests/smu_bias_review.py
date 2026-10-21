# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import argparse
import csv
import subprocess
from pathlib import Path
from typing import Iterable

import yaml
from sw.tests.smu_setup import setup_smu
from openising import TOP_MEAS, connect_to_host_commands


CONFIG_FILE = TOP_MEAS / "sw/lib/lab_instruments/config/meas_setup.yaml"


def get_review_scaling_factors(csv_path: str | Path) -> list[int]:
    """Return the scaling factors that are present in a calibration CSV."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return []

    i = 0
    factors: set[int] = set()
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []

        for row in reader:
            if not row:
                continue
            i += 1
            for field, value in row.items():
                if value in (None, ""):
                    continue
                if "_sf" in field:
                    try:
                        factors.add(int(field.rsplit("sf", 1)[-1]))
                    except ValueError:
                        continue

    if not factors:
        return []
    return sorted(factors)


def review_rate_from_log(log_path: str | Path) -> float:
    """Compute the one-rate seen in a review log, i.e. ones / total outputs."""
    log_path = Path(log_path)
    value = 0

    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if not parts or parts[0] != "[chip]":
                continue
            if parts[1] == "TOTAL":
                value = int(parts[7][:-1]) / 100

    return value


def average_review_rates(rates: Iterable[float]) -> float:
    """Average a series of per-review rates."""
    values = list(rates)
    if not values:
        return 0.0
    return sum(values) / len(values)


def load_current_settings(csv_path: str | Path, scaling_factor: int) -> dict[str, float]:
    """Load the HUP/HDN values for one scaling factor from the calibration CSV."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Calibration CSV not found: {csv_path}")

    last_row = None
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row:
                last_row = row

    if last_row is None:
        raise ValueError(f"No calibration values available in {csv_path}")

    settings: dict[str, float] = {}
    for mode in ("hup", "hdn"):
        key = f"{mode}_sf{scaling_factor}"
        value = last_row.get(key, "")
        if value in (None, ""):
            raise ValueError(f"Missing {key} in calibration CSV for scaling factor {scaling_factor}")
        settings[mode] = float(value)
    return settings


def run_bias_review_for_scaling_factor(chip: int, core: int, scaling_factor: int, csv_path: str | Path):
    """Set the HUP/HDN bias pair for one scaling factor and run the review ELF."""

    with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
        smu_config = config["source_measure_units"]

    current_settings = load_current_settings(csv_path, scaling_factor)
    instruments = {
        "smu_3": setup_smu("smu_3", True, "current", CONFIG_FILE),
        "smu_4": setup_smu("smu_4", True, "current", CONFIG_FILE),
    }

    try:
        smu_3_mode = smu_config["smu_3"]["calibration_mode"]
        smu_4_mode = smu_config["smu_4"]["calibration_mode"]

        instruments["smu_3"].set_current_source(current_settings[smu_3_mode], smu_config["smu_3"]["voltage_limit"])
        instruments["smu_4"].set_current_source(current_settings[smu_4_mode], smu_config["smu_4"]["voltage_limit"])

        if scaling_factor < 10:
            add_zero = True
        else:
            add_zero = False
        elf_file = f"~/calibration_elfs/bias_review_core{core}_sf{'0' if add_zero else ''}{scaling_factor}.elf"
        output_file = TOP_MEAS / f"sw/tests/bias_review_core{core}_sf{scaling_factor}.log"
        subprocess.run(connect_to_host_commands + ["python3", "sw/tests/chip_test.py"], check=True)
        with output_file.open("w", encoding="utf-8") as handle:
            try:
                subprocess.run(
                    connect_to_host_commands + ["python3", "sw/uart/reset_plus_uart.py", elf_file],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            except subprocess.CalledProcessError:
                pass

        rate = review_rate_from_log(output_file)
        print(f"sf={scaling_factor}: rate={rate:.6f}")
        return rate
    finally:
        for instrument in instruments.values():
            instrument.disable_output()


def run_bias_reviews(chip: int, core: int, csv_path: str | Path | None = None) -> float:
    """Run all bias reviews packed by scaling factor and print the average rate."""
    csv_path = (
        Path(csv_path)
        if csv_path is not None
        else TOP_MEAS / f"openising/calibration_currents/currents_chip{chip}_core{core}.csv"
    )
    if not csv_path.exists():
        raise FileNotFoundError(f"Calibration CSV not found: {csv_path}")

    factors = get_review_scaling_factors(csv_path)
    if not factors:
        raise ValueError(f"No HUP/HDN bias values found in {csv_path}")

    rates = []
    for scaling_factor in factors:
        rates.append(run_bias_review_for_scaling_factor(chip, core, scaling_factor, csv_path))

    average_rate = average_review_rates(rates)
    print(f"Average bias review rate across {len(rates)} scaling factors: {average_rate:.6f}")
    return average_rate


def main():
    parser = argparse.ArgumentParser(description="Run the bias-review sequence across all calibration scaling factors.")
    parser.add_argument("--chip", type=int, required=True, help="Chip index used for the calibration CSV name.")
    parser.add_argument("--core", type=int, default=1, help="Core index used for the calibration CSV and ELF names.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional calibration CSV path; defaults to the chip/core CSV in TOP_MEAS.",
    )
    args = parser.parse_args()

    run_bias_reviews(chip=args.chip, core=args.core, csv_path=args.csv)


if __name__ == "__main__":
    run_bias_reviews(chip=2, core=1)
