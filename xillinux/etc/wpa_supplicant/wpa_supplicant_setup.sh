#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Bob Vanhoof
# 19 March 2021

# make backup
cp wpa_supplicant.conf wpa_supplicant.conf.bak

# query password
echo "enter esat password (characters not shown):"
read -s pass

# function to hash your bloody password
sed -i -e "s@password=.*@password=hash:$(echo -n $pass | iconv -t utf16le | openssl dgst -md4 -provider legacy -provider default | sed -e 's/.*= //')@" /etc/wpa_supplicant/wpa_supplicant.conf

#query username
echo "enter esat username:"
read  user
sed -i -e "s/identity=.*/identity=\"$user@esat.kuleuven.be\"/" /etc/wpa_supplicant/wpa_supplicant.conf
