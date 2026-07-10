# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import threading
import requests

from contextlib import contextmanager
from typing import Tuple

from .crypto_utils import Credentials

ICLAB_BASE_URL = "https://securewww.esat.kuleuven.be/iclab"
ICLAB_LANDING_URL = f"{ICLAB_BASE_URL}/"
ICLAB_KEEPALIVE_URL = f"{ICLAB_BASE_URL}/lab-control.php"

class _ICLabKeepAlive:
    """Keeps IC-LAB firewall access alive for the lifetime of a session."""
    def __init__(
        self,
        session: requests.Session,
        auth: Credentials,
        keepalive_period_s: float,
        request_timeout_s: float,
    ) -> None:
        self._session = session
        self._auth = auth
        self._keepalive_period_s = keepalive_period_s
        self._request_timeout_s = request_timeout_s
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        # Establish authenticated session first, then trigger the first refresh.
        self._request(ICLAB_LANDING_URL)
        self._request(ICLAB_KEEPALIVE_URL)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self._keepalive_period_s + self._request_timeout_s)

    def _run(self) -> None:
        while not self._stop_event.wait(self._keepalive_period_s):
            self._request(ICLAB_KEEPALIVE_URL)

    def _request(self, url: str) -> requests.Response:
        response = self._session.get(
            url,
            auth=(self._auth.username, self._auth.password), # converting to tuple for get API
            verify=True,
            timeout=self._request_timeout_s,
        )
        response.raise_for_status()
        return response

@contextmanager
def iclab_session(
    key: Credentials,
    keepalive_period_s: float = 59.0,
    request_timeout_s: float = 10.0,
):
    """
    Context manager for managing an ICLab session.
    This function creates a session with the ICLab API and ensures that the session is properly closed after use.
    Yields:
        requests.Session: A session object for making requests to the ICLab API.
    """
    auth = key
    session = requests.Session()
    keepalive = _ICLabKeepAlive(
        session=session,
        auth=auth,
        keepalive_period_s=keepalive_period_s,
        request_timeout_s=request_timeout_s,
    )
    keepalive.start()

    try:
        yield session
    finally:
        keepalive.stop()
        session.close()
