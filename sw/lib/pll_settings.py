# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene
# Goal: Collect all settings for PLL in file for easy import


from sw.lib.pll_command_api import DEFAULT_CFG


PLL_BYPASS_CFG = DEFAULT_CFG.copy()
PLL_BYPASS_CFG.update(set_clk_out=1, set_div_freq=0b000, pll_clk_o_en=1)
PD_DEBUG_CFG = DEFAULT_CFG.copy()
PD_DEBUG_CFG.update(set_fb_mux=0b10, set_v_ctrl=0b10)
PD_OFF_CFG = DEFAULT_CFG.copy()
PD_OFF_CFG.update(pdown_PD=0b1, pdown_VCO=0b1, set_v_ctrl=0b10)
VCO_CHARAC_CFG = DEFAULT_CFG.copy()
VCO_CHARAC_CFG.update(pdown_PD=0b1, set_v_ctrl=0b11)
SAFE_LOOP_CFG = DEFAULT_CFG.copy()
SAFE_LOOP_CFG.update(set_current=0b001, set_c1=0b111, set_c2=0b111, set_r1=0b011, set_v_ctrl=0b00)  # Min BW
COOKED_CFG = SAFE_LOOP_CFG.copy()
COOKED_CFG.update(set_v_ctrl=0b00, vco_current_min=0b1000, vco_current_max=0b1100, vco_tune_coarse=0b1001)
FREF_20M_CFG = DEFAULT_CFG.copy()
FREF_20M_CFG.update(
    clk_div_val=49,
    set_div_freq=0b010,
    set_v_ctrl=0b00,
    vco_current_min=0b0011,
    vco_current_max=0b0000,
    vco_tune_coarse=0b0011,
)

# Fref = 4 MHz
# Reference on sample 3 tested 3.2MHz to 5 MHz
CFG_REF4 = DEFAULT_CFG.copy()
CFG_REF4.update(
    clk_div_val=49,
    set_v_ctrl=0b00,
    vco_tune_coarse=0b1111,
    vco_current_max=0b1100,
    vco_current_min=0b1011,
)

CFG_REF4_OUT32MHZ = CFG_REF4.copy()
CFG_REF4_OUT32MHZ.update(
    set_div_freq=0b100,
)
CFG_REF4_OUT64MHZ = CFG_REF4.copy()
CFG_REF4_OUT64MHZ.update(
    set_div_freq=0b011,
)
CFG_REF4_OUT128MHZ = CFG_REF4.copy()
CFG_REF4_OUT128MHZ.update(
    set_div_freq=0b010,
)
CFG_REF4_OUT256MHZ = CFG_REF4.copy()
CFG_REF4_OUT256MHZ.update(
    set_div_freq=0b001,
)

# Fref = 8 MHz, VCO out is 8*128 = 1024 MHz
# 7 to 9 MHz for sample 3
CFG_REF8 = DEFAULT_CFG.copy()
CFG_REF8.update(
    clk_div_val=49,
    set_v_ctrl=0b00,
    vco_tune_coarse=0b1000,
    vco_current_max=0b0000,
    vco_current_min=0b1100,
)

CFG_REF8_OUT8MHZ = CFG_REF8.copy()
CFG_REF8_OUT8MHZ.update(
    set_div_freq=0b111,
)
CFG_REF8_OUT16MHZ = CFG_REF8.copy()
CFG_REF8_OUT16MHZ.update(
    set_div_freq=0b110,
)
CFG_REF8_OUT32MHZ = CFG_REF8.copy()
CFG_REF8_OUT32MHZ.update(
    set_div_freq=0b101,
)
CFG_REF8_OUT64MHZ = CFG_REF8.copy()
CFG_REF8_OUT64MHZ.update(
    set_div_freq=0b100,
)
CFG_REF8_OUT128MHZ = CFG_REF8.copy()
CFG_REF8_OUT128MHZ.update(
    set_div_freq=0b011,
)
CFG_REF8_OUT256MHZ = CFG_REF8.copy()
CFG_REF8_OUT256MHZ.update(
    set_div_freq=0b010,
)
# We pushed this one with ref 9.1 output 580MHz the uart test succeeded
CFG_REF8_OUT512MHZ = CFG_REF8.copy()
CFG_REF8_OUT512MHZ.update(
    set_div_freq=0b001,
)


# DEFAULT_CFG = {
#     "fb_clk_oen": 0b1,  # ?
#     "pll_clk_o_en": 0b0,  # clk_o comes from the divider outside the PLL
#     "clk_div_val": 4,  # divider outside IP, divides frequency by 4+1
#     "clk_div_en": 0b1,  # enabled divider outside the PLL
#     "pdown_PD": 0b0,  # PLL enabled
#     "pdown_VCO": 0b0,  # PLL enabled
#     "set_current": 0b011,  # Icp = pll_iref_i (check)
#     "set_c1": 0b011,  # C1 = 20 pF (check)
#     "set_c2": 0b011,  # C2 = 500 fF (check)
#     "set_r1": 0b011,  # R1 = 5 kOhm (check)
#     "vco_tune_coarse": 0b1010,
#     "vco_current_min": 0b1100,
#     "vco_current_max": 0b1101,
#     "set_v_ctrl": 0b10,  # Debug mode, 00 for default and 11 for out pad
#     "set_clk_out": 0b0,  # PLL loop closed, 1 for CLK_EXT
#     "set_div_freq": 0b010,  # Ndiv = 4
#     "set_fb_mux": 0b00,  # Loop closed, 01 for loop broken and F_FB used,
#     # 10 for clock buffered to F_FB and loop closed
# }
