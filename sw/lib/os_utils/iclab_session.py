# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import requests
from contexlib import contextmanager

@contextmanager
def iclab_session(key: tuple[str, str]):
    """
    Context manager for managing an ICLab session.
    This function creates a session with the ICLab API and ensures that the session is properly closed after use.
    Yields:
        requests.Session: A session object for making requests to the ICLab API.
    """
    username, password = key
    session = requests.Session()

    # Authenticate
    r = session.get(
        "https://securewww.esat.kuleuven.be/iclab/",
        auth=(username, password),
        verify=False,   # equivalent to curl -k
    )
    r.raise_for_status()

    try:
        yield session
    finally:
        session.close()
