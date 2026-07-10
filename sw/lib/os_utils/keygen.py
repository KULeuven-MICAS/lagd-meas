# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

from getpass import getpass
from crypto_utils import create_keyfile

filename = input("Output key file [credentials.key]: ").strip()
if filename == "":
    filename = "credentials.key"

username = input("University username: ")

password = getpass("University password: ")

master1 = getpass("Choose a master password: ")
master2 = getpass("Repeat master password: ")

if master1 != master2:
    raise SystemExit("Master passwords do not match.")

create_keyfile(
    filename,
    username,
    password,
    master1,
)

print(f"Encrypted credential file written to '{filename}'.")
