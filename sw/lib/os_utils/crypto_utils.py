# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

# This module provides utility functions for encrypting and decrypting credentials
#   using a master password.

import os
import yaml
import base64

from pathlib import Path
from getpass import getpass
from dataclasses import dataclass
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Parameters for scrypt
SALT_SIZE = 16
N = 2**14
R = 8
P = 1

@dataclass
class Credentials:
    username: str
    password: str


def derive_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive a Fernet-compatible key from the master password.
    """
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=N,
        r=R,
        p=P,
    )

    key = kdf.derive(master_password.encode("utf-8"))

    # Fernet expects urlsafe base64
    return base64.urlsafe_b64encode(key)


def create_keyfile(filename, username, password, master_password):
    salt = os.urandom(SALT_SIZE)

    key = derive_key(master_password, salt)
    cipher = Fernet(key)

    credentials = {
        "username": username,
        "password": password,
    }

    encrypted = cipher.encrypt(yaml.dump(credentials).encode())

    data = {
        "version": 1,
        "kdf": "scrypt",
        "salt": base64.b64encode(salt).decode(),
        "ciphertext": base64.b64encode(encrypted).decode(),
    }

    with Path(filename).open("w") as f:
        yaml.dump(data, f, indent=2)


def load_credentials(filename, master_password):
    with Path(filename).open() as f:
        data = yaml.safe_load(f)
    salt = base64.b64decode(data["salt"])
    encrypted = base64.b64decode(data["ciphertext"])

    key = derive_key(master_password, salt)
    cipher = Fernet(key)

    try:
        plaintext = cipher.decrypt(encrypted)
    except InvalidToken:
        raise ValueError("Invalid master password")

    credentials = yaml.load(plaintext, Loader=yaml.FullLoader)

    return credentials["username"], credentials["password"]

def decrypt_keyfile(filename: str) -> Credentials:
    """
    Load credentials from an encrypted key file.
    """
    master_password = getpass("Master password: ")

    try:
        username, password = load_credentials(
            filename,
            master_password
        )
    except ValueError as e:
        raise SystemExit("Incorrect master password.") from e

    print("Successfully decrypted credentials.")
    return Credentials(username=username, password=password)

