This folder contains the compiled elf files for chip functional verification.

- *helloworld.spm.elf:* tests on the bootrom and stack memory. It will prints out "Hello World!" in the terminal. If it finishes correctly, it proves the interface, bootrom, and the stack memory work.

- *lagd_reg.spm.elf:* tests all the cpu-writable registers within both Ising cores. If the chip does not have any stuck-at fault, it should report no error.

- *lagd_scompute.spm.elf:* tests the single-core's function and printf function.

- *lagd_dcompute.spm.elf:* tests if the measurement setup can catch an error when an error code is returned. The program will return an error code (0x3) and print "FAIL" in the terminal.
