# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

declare -A mnt_path=(
    [jsun]="/users/micas/jsun/sunjc/codes/aria_project/tapeout/lagd-meas/sw"
    [sdeweer]="/esat/micas-lapserv21/users/sdeweer/gitrepos/lagd-im/tools/zedboard_python"
    [gsarda]="/users/micas/gsarda/ising/lagd-meas/"
)

mnt_dir="/root/Workspace"
declare -A mnt_pnt=(
    [jsun]="$mnt_dir/workspace_jiacong"
    [sdeweer]="$mnt_dir/workspace_sofie"
    [gsarda]="$mnt_dir/gsarda_wsp"
)

declare -A server=(
    [jsun]="neptune.esat.kuleuven.be"
    [sdeweer]="neptune.esat.kuleuven.be"
    [gsarda]="eridani"
)

declare -A key=(
    [jsun]=""
    [sdeweer]=""
    [gsarda]="/root/.ssh/gs_rsa"
)