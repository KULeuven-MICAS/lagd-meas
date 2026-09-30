This folder contains the calibration look-up table for the bias current required by the analog macro.

The analog macro requires different current bias when the scaling factor (sf, range: 1-31, type: int) differs.

The [current_chip2_core1.csv](./currents_chip2_core1.csv) saves the look-up table for chip #2. Unit: A.

*base:* bias current for J pull-down path.

*j:* bias current for J pull-up path.

*hup_sf(#):* bias current for h pull-up path.

*hdn_sf(#):* bias current for h pull-down path.
