#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Bob Vanhoof
# 19 March 2021
#
# Since the network interface cannot connect due to an invalid certificate
#  since no RTC clock is provided, which sets the date automatically to something in 2016
# - set the date to a valid date of the certificate
# - reboot the network interface

sudo timedatectl set-timezone Europe/Brussels
date --set="04 AUG 2026 00:00"
service networking restart
