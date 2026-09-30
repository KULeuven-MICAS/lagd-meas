# Copyright 2024 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Common OpenOCD script for Cheshire.
# Based on: cheshire/util/openocd.common.tcl, cheshire repository [commit: 55650af]
# Changes by Jiacong Sun:
# - Reduced to DEFINITIONS ONLY (tap + target + riscv settings). No actions:
#   init/halt, port config, and the gdb-detach handler now live in the caller
#   (openocd.run.tcl / openocd.server.tcl), so this file is reusable by both.
#
# Source AFTER an adapter config (openocd.ft4232.tcl).

reset_config none

set _CHIPNAME riscv
jtag newtap $_CHIPNAME cpu -irlen 5 -expected-id 0x1c5e5db3

set _TARGETNAME $_CHIPNAME.cpu
target create $_TARGETNAME riscv -chain-position $_TARGETNAME -coreid 0

gdb report_data_abort enable
gdb report_register_access_error enable

riscv set_command_timeout_sec 5

# Default memory access via the CPU program buffer. Callers that need to access
# memory while the core RUNS (e.g. polling EOC in openocd.run.tcl) switch this to
# prefer the debug system bus (SBA).
riscv set_mem_access progbuf sysbus

# Translate virtual addresses by walking the page tables in OpenOCD.
riscv virt2phys_mode sw
