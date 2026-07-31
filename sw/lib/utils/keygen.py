# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import logging
import sys
from getpass import getpass

from crypto import create_keyfile
from iclab_session import prompt_for_credentials

logger = logging.getLogger(__name__)

logging_level = logging.INFO
logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)

filename = input("Output key file [credentials.key]: ").strip()
if filename == "":
    filename = "credentials.key"

credentials = prompt_for_credentials()

master1 = getpass("Choose a master password: ")
master2 = getpass("Repeat master password: ")
if master1 != master2:
    raise SystemExit("Master passwords do not match.")

create_keyfile(
    filename,
    credentials.username,
    credentials.password,
    master1,
)

logger.info(f"Encrypted credential file written to '{filename}'.")
