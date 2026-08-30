# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Author: Sofie De Weer <sofie.deweer@kuleuven.be>
import logging
import numpy as np
from pathlib import Path
import subprocess
from openising import TOP_MEAS

from sw.lib.lab_instruments.drivers.keysight_smu_b2900 import KeysightSMUB2900

def calibrate_smu(smu:KeysightSMUB2900, minCurrent, maxCurrent, stepCurrent, complianceVoltage, calibrateMode:str):
    prepare_command = ["ssh", "-t", "root@10.88.18.5","cd Workspace/workspace_jiacong &&", "source env.sh &&"]
    smu.set_current_source(minCurrent, complianceVoltage)
    smu.enable_output()
    output_file = TOP_MEAS / "sw/tests/smu_calibration_results.log"
    currents = np.arange(minCurrent, maxCurrent, stepCurrent)
    for current in currents:
        subprocess.run(prepare_command +[ "python3", "sw/tests/chip_test.py"], check=True, )
        smu.set_current_source(current, complianceVoltage)
        # Calibrate j,h or scaling factor
        
        if calibrateMode == "j":
            with output_file.open("w") as f:
                subprocess.run(prepare_command +[  "python3 sw/uart/send_uart.py --timeout 600 ~/mnt/tbettens-lagd/submodules/lagd-im/sw/tests/galena/scenarios/calibrate_j.spm.elf --verify"], check=True, stdout=f, stderr=subprocess.STDOUT)
            if count_zeros_ones(output_file):
                logging.info(f"Current {current} A: calibration successful")
                break
        elif calibrateMode == "h":
            pass
        elif calibrateMode == "scaling":
            pass
        else:
            raise ValueError(f"Invalid calibrate mode: {calibrateMode}")
    smu.disable_output()

def count_zeros_ones(file:Path, nb_samples:int=1000):
    nb_zeros = 0
    with file.open("r") as f:
        for line in f.readlines():
            nb_zeros += int(line[-1] == 0)
    nb_zeros /= nb_samples
    return np.isclose(nb_zeros, 0.5, rtol=0.1, atol=0.05)

