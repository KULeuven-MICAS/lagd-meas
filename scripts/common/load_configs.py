# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import yaml
from pathlib import Path

ZEDB_LAGD_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "zedb_lagd.yml"

def load_configs(config_file_path):
    """Load configuration from a YAML file."""
    with Path.open(config_file_path, 'r', encoding='utf-8') as f:
        configs = yaml.safe_load(f)
    return configs

def load_zedb_lagd_configs():
    """Load the ZEDB LAGD configuration from the default YAML file."""
    return load_configs(ZEDB_LAGD_CONFIG_PATH)
