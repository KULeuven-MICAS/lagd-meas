# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# The source script is from Robin Geens
#
# drc_waiver.tcl — pre-hook for write_bitstream
#
# PS_GPIO[24:29] are processor native pads intentionally detached from PL logic.
# They carry no IOSTANDARD/LOC constraints by design; demote to warnings so
# bitstream generation is not blocked.
set_property SEVERITY {Warning} [get_drc_checks NSTD-1]
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]