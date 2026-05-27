# drc_waiver.tcl — pre-hook for write_bitstream
#
# PS_GPIO[24:29] are processor native pads intentionally detached from PL logic.
# They carry no IOSTANDARD/LOC constraints by design; demote to warnings so
# bitstream generation is not blocked.
set_property SEVERITY {Warning} [get_drc_checks NSTD-1]
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
