# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Author: Sofie De Weer <sofie.deweer@kuleuven.be>
import numpy as np
from pathlib import Path
import subprocess
from functools import partial
from openising import TOP_MEAS, connect_to_host_commands

from sw.lib.lab_instruments.drivers.keysight_smu_b2900 import KeysightSMUB2900


def validate_calibration_range(calibrateMode: str, minCurrent: float, maxCurrent: float, scalingFactor: int = 1):
    """Guard the current sweep against the B2901BL absolute current limit.

    The calibration sweep is always evaluated in absolute-current magnitude, and
    every HUP/HDN scaling factor multiplies the configured current span by the
    same factor.  If the scaled range exceeds the instrument limit, fail fast
    instead of sending a dangerous setpoint to the SMU.
    """
    if calibrateMode not in ["j", "hup", "hdn"]:
        raise ValueError(f"Invalid calibrate mode: {calibrateMode}")

    scaled_min = abs(minCurrent) * abs(scalingFactor)
    scaled_max = abs(maxCurrent) * abs(scalingFactor)
    limit = KeysightSMUB2900.MAX_CURRENT_A
    if scaled_min > limit or scaled_max > limit:
        raise ValueError(
            f"Calibration range for {calibrateMode} with sf={scalingFactor} "
            f"exceeds B2901BL limit: [{scaled_min:.6g}, {scaled_max:.6g}] A > {limit:.6g} A"
        )
    return scaled_min, scaled_max


def find_transition_interval(low, high, response_fn: callable, threshold=0.5, max_iter=8):
    """Binary-search for the transition band between mostly-zero and mostly-one responses.

    ``low`` is the current closest to 0 A and ``high`` is the current farthest
    from 0 A.  The sign matters: for negative currents, the one-fraction grows as
    the magnitude increases; for positive currents, the one-fraction shrinks as the
    magnitude increases.  The search therefore follows the sign-specific direction
    while still using a binary-search pattern.
    """
    if low == high:
        return low, high

    low_value = response_fn(low)
    high_value = response_fn(high)

    if low_value >= threshold and high_value >= threshold:
        return low, high
    if low_value < threshold and high_value < threshold:
        return low, high

    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        mid_value = response_fn(mid)

        if low < 0:
            # Negative branch: farther from zero => more ones
            if mid_value < threshold:
                low = mid
                low_value = mid_value
            else:
                high = mid
                high_value = mid_value
        else:
            # Positive branch: farther from zero => more zeros
            if mid_value >= threshold:
                low = mid
                low_value = mid_value
            else:
                high = mid
                high_value = mid_value

    return low, high


def measure_transition_metric(
    smu: KeysightSMUB2900,
    current: float,
    complianceVoltage: float,
    elf_file: str,
    output_file: Path,
    connect_to_host_commands: list[str],
):
    """Measure the one-fraction for a single current point."""
    subprocess.run(
        connect_to_host_commands + ["python3", "sw/tests/chip_test.py"],
        check=True,
    )
    smu.set_current_source(current, complianceVoltage)
    with output_file.open("w") as f:
        try:
            subprocess.run(
                connect_to_host_commands
                + [
                    "python3",
                    "sw/uart/send_uart.py",
                    "--timeout 5",
                    elf_file,
                    "--verify",
                ],
                stdout=f,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError:
            pass
    _, nb_ones, nb_zeros = count_zeros_ones(output_file)
    return nb_ones / max(1, nb_ones + nb_zeros)


def transition_score(
    current: float,
    smu: KeysightSMUB2900,
    complianceVoltage: float,
    elf_file: str,
    output_file: Path,
    connect_to_host_commands: list[str],
) -> float:
    """Return the one-fraction at a given current for broad-search bracket selection."""
    return measure_transition_metric(
        smu=smu,
        current=current,
        complianceVoltage=complianceVoltage,
        elf_file=elf_file,
        output_file=output_file,
        connect_to_host_commands=connect_to_host_commands,
    )


def calibrate_smu(
    smu: KeysightSMUB2900,
    calibrateMode: str,
    minCurrent: float,
    maxCurrent: float,
    coarseStep: float,
    complianceVoltage: float = 0.75,
    scalingFactor: int = 1,
    core: int = 1,
) -> float:
    """Calibrates an smu to the correct current.

    @type smu: KeysightSMUB2900
    @param smu: the smu to calibrate
    @type minCurrent: float
    @param minCurrent: the minimum current in which to sweep in Ampere.
    @type maxCurrent: float
    @param maxCurrent: the maximum current in which to sweep in Ampere.
    @type stepCurrent: float
    @param stepCurrent: the stepsize for the sweep, in Ampere.
    @type complianceVoltage: float
    @param complianceVoltage: the limit voltage. Default set to 0.75V.
    @type calibrateMode: str
    @param calibrateMode: which setting to calibrate. Can be j, hup or hdn.
    @type scalingFactor: int
    @param scalingFactor: the scaling factor for h for which to calibrate. Defaults to 1.
    @type cor: int
    @param core: the core on which to calibrate. Defaults to 1.
    @rtype: float
    @return: the best current setting
    """
    validate_calibration_range(calibrateMode, minCurrent, maxCurrent, scalingFactor)

    smu.set_current_source(minCurrent, complianceVoltage)
    smu.enable_output()
    output_file = TOP_MEAS / "sw/tests/smu_calibration_results.log"

    if scalingFactor < 10:
        sf = f"_sf0{scalingFactor}"
    else:
        sf = f"_sf{scalingFactor}"
    if calibrateMode in ["j", "hup", "hdn"]:
        elf_file = f"~/calibration_elfs/calibrate_{calibrateMode}_core{core}{sf if calibrateMode != 'j' else ''}.elf"
    else:
        raise ValueError(f"Invalid calibrate mode: {calibrateMode}")
    lower = minCurrent * scalingFactor
    upper = maxCurrent * scalingFactor


    response_fn = partial(
        transition_score,
        smu=smu,
        complianceVoltage=complianceVoltage,
        elf_file=elf_file,
        output_file=output_file,
        connect_to_host_commands=connect_to_host_commands,
    )
    low, high = find_transition_interval(
        lower,
        upper,
        response_fn,
        threshold=0.5,
        max_iter=6,
    )

    fineStep=np.sign(low)*0.5e-6
    fine_currents = np.arange(low, high + fineStep, fineStep)
    print(fine_currents)

    # new_min = None
    # new_max = None
    # for current in fine_currents:
    #     value = measure_transition_metric(
    #         smu=smu,
    #         current=current,
    #         complianceVoltage=complianceVoltage,
    #         elf_file=elf_file,
    #         output_file=output_file,
    #         connect_to_host_commands=connect_to_host_commands,
    #     )
    #     if value >= 0.5 and new_min is None:
    #         new_min = current
    #     elif value < 0.5 and new_max is None:
    #         new_max = current
    #     if new_min is not None and new_max is not None:
    #         break

    # if new_min is None:
    #     new_min = low
    # if new_max is None:
    #     new_max = high

    # fineStep = 0.5e-6 * np.sign(new_min)

    # currents = np.arange(new_min, new_max + fineStep, fineStep)
    compliances = []


    for current in fine_currents:
        subprocess.run(
            connect_to_host_commands + ["python3", "sw/tests/chip_test.py"],
            check=True,
        )
        smu.set_current_source(current, complianceVoltage)
        # Calibrate j,hup or hdn
        with output_file.open("w") as f:
            try:
                subprocess.run(
                    connect_to_host_commands
                    + [
                        "python3",
                        "sw/uart/send_uart.py",
                        "--timeout 5",
                        elf_file,
                        "--verify",
                    ],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError:
                pass
        compliances.append(count_zeros_ones(output_file)[0])

    best_current = fine_currents[np.argmin(compliances)]
    smu.set_current_source(best_current, complianceVoltage)
    smu.measure()
    # smu.disable_output()
    return best_current


def count_zeros_ones(file: Path):
    nb_zeros = 0
    nb_ones = 0
    with file.open("r") as f:
        for line in f.readlines():
            line_split = line.split(" ")
            if line_split[0] == "[chip]":
                nb_zeros += int(line_split[-1] == "0\n")
                nb_ones += int(line_split[-1] == "1\n")
    assert max(nb_zeros, nb_ones) > 0
    return np.abs(nb_zeros - nb_ones) / max(nb_zeros, nb_ones), nb_ones, nb_zeros
