# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Network check: *IDN? of the instruments of meas_setup.yaml listed in KEYS (TCPIP::<IP>::inst0::INSTR, no reset).
# Run: python sw/tests/lan_check.py

from pathlib import Path

import pyvisa
import yaml

KEYS = ("function_generator", "power_supply_pll", "scope_mxr")  # on the private network 10.88.18.x since 2026-11-09

cfg_path = Path(__file__).resolve().parents[1] / "lib" / "lab_instruments" / "config" / "meas_setup.yaml"
config = yaml.safe_load(cfg_path.read_text())
rm = pyvisa.ResourceManager()
for key in KEYS:
    resource = "TCPIP::{}::inst0::INSTR".format(config[key]["IP"])
    try:
        inst = rm.open_resource(resource)
        inst.timeout = 5000  # ms
        try:
            print("{:20s} {:40s} OK   {}".format(key, resource, inst.query("*IDN?").strip()))
        finally:
            inst.close()
    except Exception as e:
        print("{:20s} {:40s} FAIL {!r}".format(key, resource, e))
