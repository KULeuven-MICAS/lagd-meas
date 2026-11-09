# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Connection check of the Keysight MXR058A over USB (meas_setup.yaml `scope_mxr`, args.resource), without the reset
# the driver does on opening: only *IDN?, first through pyvisa-py, then through python-usbtmc (pip install
# python-usbtmc; a separate USBTMC implementation on pyusb). Run: python sw/tests/mxr_usb_check.py

RESOURCE = "USB0::10893::36871::MY61190114::0::INSTR"
VENDOR, PRODUCT = 0x2A8D, 0x9007  # Keysight, MXR058A

print("--- pyvisa-py")
try:
    import pyvisa

    rm = pyvisa.ResourceManager()
    print("VISA sees:", rm.list_resources())
    scope = rm.open_resource(RESOURCE)
    scope.timeout = 10000  # ms
    try:
        print("*IDN? ->", scope.query("*IDN?").strip())
    finally:
        scope.close()
except Exception as e:
    print("FAILED:", repr(e))

print("--- python-usbtmc")
try:
    import usbtmc

    scope = usbtmc.Instrument(VENDOR, PRODUCT)
    scope.timeout = 10  # s
    try:
        print("*IDN? ->", scope.ask("*IDN?").strip())
    finally:
        scope.close()
except ImportError:
    print("not installed: pip install python-usbtmc")
except Exception as e:
    print("FAILED:", repr(e))
