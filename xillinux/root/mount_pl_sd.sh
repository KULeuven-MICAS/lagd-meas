#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Description: Mount the SD card partition to /mnt/pl_sd if not already mounted.

mkdir -p /mnt/pl_sd
if ! findmnt -rn -o TARGET | grep -q "^/mnt/pl_sd$"; then
    mount /dev/mmcblk0p1 /mnt/pl_sd
fi
