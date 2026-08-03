#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Bob Vanhoof
# 19 March 2021

# make backup
cp wpa_supplicant.conf wpa_supplicant.conf.bak

# query password
echo "Enter ESAT password (characters not shown):"
read -r -s pass
echo ""

# Hash password for MSCHAPv2 (NT hash) and update wpa_supplicant.conf
hash="$(printf '%s' "$pass" | iconv -t utf16le | openssl dgst -md4 -provider legacy -provider default | sed -e 's/.*= //')"
sed -i -e "s@password=.*@password=hash:${hash}@" /etc/wpa_supplicant/wpa_supplicant.conf

#query username
echo "Enter ESAT username:"
read -r user
sed -i -e "s/identity=.*/identity=\"$user@esat.kuleuven.be\"/" /etc/wpa_supplicant/wpa_supplicant.conf
