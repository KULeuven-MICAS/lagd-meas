This file shows the expected output of all the basic galena + digital tests. Every test consists of 2 elf files: <test_name>_galena.spm.elf and <test_name>.spm.elf. The first one is used to set up galena, the second one is to run the test. In order to run a test do the following steps:

```bash
ssh root@10.88.18.5
cd Workspace/workspace_sofie 
source env.sh
python sw/tests/chip_test.py
python sw/uart/send_uart.py sw/inputs/<test_name>_galena.spm.elf
python sw/tests/chip_test.py
python sw/uart/send_uart.py sw/inputs/<test_name>.spm.elf
```
On the board the files are also stored under `~/Workspace/finished_elfs/`.

# Ferromagnetic flipping

configuration file settings: 76 zeros, 180 ones, add_h = False, nb_flipping = 10. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 0. In the base_experiment.yaml the cluster_choice = 'test' and the init_cluster_size: 0.0625.

```
[chip] spin_fifo_data_0[1]: 0000fffffffffffffffffffffffffffffffffffffffff0000000000000000000
[chip] spin_fifo_data_1[1]: ffff000000000000000fffffffffffffffffffffffffffffffffffffffffffff
```
# Ferromagnetic with bias and flipping

configuration file settings: 180 zeros, 76 ones, add_h = True, nb_flipping = 3, sign_h = -7. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1. And add in lagd_scompute.spm.c `lagd_print_debug_fm_spin_out_data(CORE_TESTED);` on line 102. In the base_experiment.yaml the cluster_choice = 'test' and the init_cluster_size: 0.996.

```
[chip] spin_fifo_data_0[1]: 0000000000000000000000000000000000000000000000000000000000000000
[chip] spin_fifo_data_1[1]: 0000000000000000000000000000000000000000000000000000000000000000
[chip] debug_fm_spin_out_data[1]: fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffc
```
# Ferromagnetic to 0
As a lot of bugs are cleared after this run, you won't get fully the same answers. The probable outcome would be that the second line also is all 0's. 

configuration file settings: 200 zeros, 56 ones, add_h = False, nb_flipping = 1. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1.

```
[chip] spin_fifo_data_0[1]: 0000000000000000000000000000000000000000000000000000000000000000
[chip] spin_fifo_data_1[1]: 00000000000000000000000000000000000000000000000000ffffffffffffff
```
# Ferromagnetic to 1

As a lot of bugs are cleared after this run, you won't get fully the same answers. The probable outcome would be that the second line also is all 1's. 

configuration file settings: 56 zeros, 200 ones, add_h = False, nb_flipping = 1. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1.

```
[chip] spin_fifo_data_0[1]: ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
[chip] spin_fifo_data_1[1]: 00000000000000ffffffffffffffffffffffffffffffffffffffffffffffffff
```
# Ferromagnetic bias to 0
As a lot of bugs are cleared after this run, you won't get fully the same answers. The probable outcome would be that the second line also is all 0's. 

configuration file settings: 56 zeros, 200 ones, add_h = True, sign_h = -7, nb_flipping = 1. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1.
```
[chip] spin_fifo_data_0[1]: 0000000000000000000000000000000000000000000000000000000000000000
[chip] spin_fifo_data_1[1]: 0000000000000000000fffffffffffffffffffffffffffffffffffffffffffff
```
# Ferromagnetic bias to 1
As a lot of bugs are cleared after this run, you won't get fully the same answers. The probable outcome would be that the second line also is all 1's. 

configuration file settings: 200 zeros, 56 ones, add_h = True, sign_h = 7, nb_flipping = 1. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1.
```
[chip] spin_fifo_data_0[1]: ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
[chip] spin_fifo_data_1[1]: 000000000000000000000000000000000000000000000fffffffffffffffffff
```
# Anti-ferromagnetic
As a lot of bugs are cleared after this run, you won't get fully the same answers. The probable outcome would be that the second line also is a random answer. 

configuration file settings: 56 zeros, 200 ones, add_h = False, nb_flipping = 1. In the lagd_reg_params.h in lagd-im submodule change lines 19 and 20 to 1.

```
[chip] spin_fifo_data_0[1]: ffeb67f2cf6eeec84aea8b70ca2370771dbfdff4fbf5befb6ff7ff7d7afe7eff
[chip] spin_fifo_data_1[1]: 00000000000000ffffffffffffffffffffffffffffffffffffffffffffffffff
```