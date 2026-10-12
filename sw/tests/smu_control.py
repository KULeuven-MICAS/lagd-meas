# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Toon Bettens <toon.bettens@kuleuven.be>

"""Set a current on one SMU and read back the voltage.

    python -m sw.tests.smu_control --smu jup --current 100e-6
    python -m sw.tests.smu_control --smu 10.91.16.42 --current 100e-6

--smu takes either one of the bias names below or a literal address.
The output is switched off again on the way out, on every path.
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keysight_smu_b2900 import KeysightSMUB2900
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser

logger = logging.getLogger(__name__)

PRJ_ROOT = Path(__file__).resolve().parent.parent
INSTR_CFG_PATH = PRJ_ROOT / "lib" / "lab_instruments" / "config" / "meas_setup.yaml"


def bias_smus():
    """The bias SMU addresses from meas_setup.yaml, keyed by node name."""
    with INSTR_CFG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh).get("bias_smus", {})


def resolve_smu(target, known):
    """Map a bias name to its address, or pass a literal address through.

    Anything that is not a known name is treated as an address, so a one-off
    instrument still works without editing meas_setup.yaml.
    """
    key = target.strip().lower()
    if key in known:
        return known[key]["IP"], key
    return target, target


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s",
                        stream=sys.stdout)

    known = bias_smus()

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smu", "--ip", dest="smu", required=True,
                    help="bias name ({}) or a literal address".format(
                        ", ".join(sorted(known))))
    ap.add_argument("--current", type=float, required=True, help="sourced current [A]")
    ap.add_argument("--compliance", type=float, default=0.75,
                    help="voltage compliance [V] (default 0.75)")
    ap.add_argument("--verbose", action="store_true", help="log every SCPI command")
    # IC-LAB credentials. Declared here so this script owns the whole command
    # line; Parser() would otherwise parse sys.argv itself and reject the flags
    # above. Omit all three to be prompted.
    ap.add_argument("-k", "--keyfile", help="key file path")
    ap.add_argument("-u", "--username", help="university username")
    ap.add_argument("-p", "--password", help="university password")
    args = ap.parse_args()

    ip, label = resolve_smu(args.smu, known)
    logger.info("SMU %s at %s", label, ip)

    cred_argv = []
    if args.keyfile:
        cred_argv += ["-k", args.keyfile]
    if args.username:
        cred_argv += ["-u", args.username]
    if args.password:
        cred_argv += ["-p", args.password]

    parser = Parser(cred_argv)
    with iclab_session(parser.get_credentials()):
        smu = KeysightSMUB2900(inst.BaseInstrumentData(name=f"SMU-{label}", IP=ip))
        smu.set_verbose(args.verbose)
        try:
            smu.set_current_source(args.current, args.compliance)
            smu.enable_output()
            voltage, current = smu.measure()
            logger.info("set %+.6g A -> %+.6g V (measured %+.6g A)",
                        args.current, voltage, current)
        finally:
            smu.close()


if __name__ == "__main__":
    main()
