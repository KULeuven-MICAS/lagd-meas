#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Description: This script is used to report the IP address of the ZedBoard (lagdboard) after it boots up and connects to the campus network.

# Notes:
# Please place this file under /usr/local/bin/report_ip.sh
# and change the email address to your own.
# Then, trigger it on reboot by entering:
#  sudo crontab -e
# and adding the following line:
#  @reboot /usr/local/bin/report_ip.sh

# Give the campus network 30 seconds to finish the 802.1X handshake and assign DHCP
sleep 30

# Grab the current IPv4 address of eth0
BOARD_IP=$(/sbin/ip -4 addr show eth0 | /bin/grep -oP '(?<=inet\s)\d+(\.\d+){3}')

# If an IP exists, email it to your inbox
if [ ! -z "$BOARD_IP" ]; then
    echo "Please edit the email in file /usr/local/bin/report_ip.sh"
    # echo "The ZedBoard (lagdboard) booted successfully. Secure SSH target IP: $BOARD_IP" | mail -s "ZedBoard Status: Online ($BOARD_IP)" -a "From: you@email" you@email
fi
