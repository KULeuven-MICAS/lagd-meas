#!/bin/bash

# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Description: a simple script to mount the remote server directory to your local FPGA folder using sshfs.

# Configuration - Customize these for your workspace
PORT="2222"
UNAME="username"
REMOTE_PATH="/PATH/AT/REMOTE/SERVER/"
LOCAL_DIR="/PATH/ON/LOCAL/FPGA/"

echo "=================================================="
echo "<F0><9F><94><84> Initializing secure bridge to Server..."
echo "=================================================="

# 1. Ensure the local mount directory exists
mkdir -p "$LOCAL_DIR"

# 2. Check if a tunnel is already active on your port
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "<E2><84><B9><EF><B8><8F>  An active network tunnel was detected on port $PORT."
else
    echo "<F0><9F><94><91> Step 1: Open gateway tunnel (Enter your server password)"
    ssh -N -f -L ${PORT}:neptune.esat.kuleuven.be:22 ${UNAME}@ssh.esat.kuleuven.be

    # Small pause to let the background fork settle
    sleep 1
fi

# 3. Mount the filesystem over the established tunnel
echo ""
echo "<F0><9F><93><82> Step 2: Mounting Neptune directory (Enter your server password again)"
sshfs ${UNAME}@localhost:${REMOTE_PATH} ${LOCAL_DIR} -p ${PORT}

# 4. Verify success
if [ $? -eq 0 ]; then
    echo ""
    echo "<E2><9C><85> Success! Your files are linked successfully."
    echo "<F0><9F><93><8D> Local Target Folder: ~/$LOCAL_DIR"
    echo "=================================================="
else
    echo ""
    echo "<E2><9D><8C> Mounting failed. Please verify your password or reset the folder."
    echo "=================================================="
fi
