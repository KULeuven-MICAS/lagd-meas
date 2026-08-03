#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Bob Vanhoof
# 19 March 2021
#
# this file fixes the long boot time, since the network interface cannot connect due an invalid certificate
#  since no RTC clock is provided, which sets the date automatically to something in 2016

sed -i -e 's/5min/30sec/' /etc/systemd/system/network-online.target.wants/networking.service
systemctl daemon-reload
