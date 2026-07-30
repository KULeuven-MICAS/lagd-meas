#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Description: a simple script to mount the remote server directory to your local FPGA folder using sshfs.

# Configuration - Customize these for your workspace
PORT="2222"
UNAME="username"
SERVERNAME="server.domain"
JUMP_HOST="jump.host.domain"
REMOTE_PATH="/PATH/AT/REMOTE/SERVER/"
# Must be an ABSOLUTE path. A relative path is resolved against the current
# working directory, so running this script from somewhere else would silently
# create and mount a second, empty folder instead of reusing this one.

LOCAL_DIR="/PATH/ON/LOCAL/FPGA/"

echo "=================================================="
echo "<F0><9F><94><84> Initializing secure bridge to Server..."
echo "=================================================="

# 1. Nothing to do if the workspace is already mounted
if mountpoint -q "$LOCAL_DIR" 2>/dev/null; then
mkdir -p "$LOCAL_DIR"
    echo "✅ Already mounted at $LOCAL_DIR. Nothing to do."
    echo "=================================================="
    exit 0
fi

# 2. Drop a stale mount left behind by a dropped connection. Without this the
#    mountpoint keeps reporting "Transport endpoint is not connected".
fusermount -u "$LOCAL_DIR" 2>/dev/null

# 3. Ensure the local mount directory exists, then make it immutable.
#    While nothing is mounted, the mountpoint is an ordinary empty directory and
#    an accidental "rm -rf" would wipe it, which is what makes the workspace
#    look lost. The immutable flag makes that deletion fail instead.
#    Undo it with: chattr -i "$LOCAL_DIR"
mkdir -p "$LOCAL_DIR"
chattr +i "$LOCAL_DIR" 2>/dev/null

# 4. Check if a tunnel is already active on your port
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "ℹ️  An active network tunnel was detected on port $PORT."
else
    echo "🔑 Step 1: Open gateway tunnel (Enter your jump password)"
    ssh -N -f -L ${PORT}:${SERVERNAME}:22 ${UNAME}@${JUMP_HOST}
    # Small pause to let the background fork settle
    sleep 1
fi

# 3. Mount the filesystem over the established tunnel
echo ""
echo "<F0><9F><93><82> Step 2: Mounting Neptune directory (Enter your server password again)"
sshfs ${UNAME}@localhost:${REMOTE_PATH} ${LOCAL_DIR} -p ${PORT}

# 5. Mount the filesystem over the established tunnel.
#    ro        : the FPGA only reads the workspace, so writes and deletes made
#                through this mount are rejected instead of reaching Neptune.
#    reconnect : survive a dropped connection instead of going stale.
echo ""
echo "📂 Step 2: Mounting Neptune directory (Enter your server password)"
sshfs -o ro,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,port=${PORT} \
      ${UNAME}@localhost:${REMOTE_PATH} "$LOCAL_DIR"

# 6. Verify success
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Success! Your files are linked successfully (read-only)."
    echo "📍 Local Target Folder: $LOCAL_DIR"
    echo "=================================================="
else
    echo ""
    echo "❌ Mounting failed. Please verify your password or reset the folder."
    echo "=================================================="
fi
