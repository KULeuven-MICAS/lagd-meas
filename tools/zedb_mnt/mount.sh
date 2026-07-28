#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Authors: 
#   Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>
#   Jiacong Sun <jiacong.sun@kuleuven.be>

set -e

UNAME=""
UNMNT=0
SCRIPT_DIR=$(realpath $(dirname "$0"))

for i in "$@"; do
    case $i in
        --user=*)
            UNAME="${i#*=}"
            ;;
        --unmount)
            UNMNT=1
            ;;
        *)
            echo "Unknown option: $i"
            ;;
    esac
done

if [ ! -n "${UNAME}" ]; then
    echo "Error: User name not specified."
    exit 1
fi

source $SCRIPT_DIR/config-mount.sh

if [ $UNMNT -eq 1 ]; then
    fusermount -u ${mnt_pnt[$UNAME]}
    echo "Unmounted ${mnt_pnt[$UNAME]}"
    exit 0
fi

mkdir -p ${mnt_pnt[$UNAME]}

sshfs ${UNAME}-${server[$UNAME]}:${mnt_path[$UNAME]} ${mnt_pnt[$UNAME]} -o IdentityFile=${key[$UNAME]} -o StrictHostKeyChecking=no
