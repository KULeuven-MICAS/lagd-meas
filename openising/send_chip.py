import os
import numpy as np

from pathlib import Path
from __init__ import TOP_MEAS

def compile_data_convergence(data_folder: Path, interface:str, nb_iteration: int):
    """Compiles data for every flipping iteration of one run.

    @type data_folder: pathlib.Path
    @param data_folder: folder where the data is stored
    @type interface: str
    @param interface: what interface to use to send the data
    @type nb_iteration: int
    @param nb_iteration: the amount of flipping iterations
    """
    folder = data_folder / "run_0"
    compile_folder = TOP_MEAS / "openising/lagd-im/sw/tests/data/default"
    lagd_folder = TOP_MEAS / "openising/lagd-im"
    rename_move_file(folder / "model", compile_folder, "model_1")
    move_to_datafolder(folder, compile_folder, 0)

    Reg_file = TOP_MEAS / "openising/lagd-im/sw/include/lagd_reg_params.h"
    it_line = 72 # line 73 but start from 0
    for it in range(nb_iteration):

        with Reg_file.open("r") as f:
            data = f.readlines()
        data[it_line] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(it)} // max: 0x0400 (1024)"
        with Reg_file.open("w") as f:
            f.writelines(data)

        elf_file = f"lagd_commands_iteration{it}"
        os.system("pixi run bash -c 'CORE_TESTED=0 ./ci/sys-run.sh --binary=sw/tests/lagd_scompute.spm.elf'")
        rename_move_file(lagd_folder / "sw/tests/lagd_scompute.spm.elf", folder, elf_file)


def compile_data(data_folders: list[Path], nb_cores: int):
    """This function parses the input data gathered from the software run and compiles it to the elf file.

    @type data_folder: Path
    @param data_folder: the top folder in which the data is stored.
    @type nb_runs: int
    @param nb_runs: the amount of runs performed
    @type nb_cores: int
    @param nb_cores: how many cores on the chip that will be used. The maximum is 2.
    """
    assert nb_cores <= 2
    lagd_folder = TOP_MEAS / "openising/lagd-im"
    os.chdir(lagd_folder)
    # copy data to folder
    compile_folder = TOP_MEAS / "openising/lagd-im/sw/tests/data/default"
    nb_runs = len(data_folders)
    for run in range(0, nb_runs, nb_cores):
        folder_1 = data_folders[run]
        rename_move_file(folder_1 / "model", compile_folder, "model_1")
        move_to_datafolder(folder_1, compile_folder, 0)
        if nb_cores == 2 and run + 1 < nb_runs:
            folder_2 = data_folders[run+1]
            move_to_datafolder(folder_2, compile_folder, 1)
            rename_move_file(folder_2 / "model", compile_folder, "model_2")
        else:
            folder_2 = None

        # make function of increasing flip iterations
        # run makefile
        elf_file = "lagd_commands.elf"
        if folder_2 is not None:
            os.system("pixi run ./ci/sys-run.sh --binary=sw/tests/lagd_dcompute.spm.elf")
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_1, elf_file)
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_2, elf_file)
        else:
            os.system("pixi run bash -c 'CORE_TESTED=0 ./ci/sys-run.sh --binary=sw/tests/lagd_scompute.spm.elf'")
            rename_move_file(lagd_folder / "sw/tests/lagd_scompute.spm.elf", folder_1, elf_file)


def send_chip(data_folder: Path, nb_cores: int, nb_runs: int, interface: str) -> int:
    """Send the data of the different software runs to the chip and wait untill the results from the chip are written\
       to a file.

    @type data_folder: pathlib.Path
    @param data_folder: the top folder where the data of all the runs and elf files are stored.
    @type nb_cores: int
    @param nb_cores: the amount of cores that will be used on chip
    @type nb_runs: int
    @param nb_runs: total amount of runs done by the software.
    @type interface: str
    @param interface: the interface used to send the data to chip. Currently supports `jtag` and `uart`.
    @rtype: int
    @return: return message for whether everything has finished correctly.
    """

    for run in range(0, int(nb_runs / 2), nb_cores):
        elf_file = data_folder / f"run_{run}/lagd_commands.elf"

        # send to chip (send_uart)
        if interface == "uart":
            send_uart_path = TOP_MEAS / "sw/uart/send_uart.py"
            dev = "/dev/ttyUSB2"
            os.system(f"python {send_uart_path} {elf_file} --device {dev} --verify")
        elif interface == "jtag":
            os.chdir(TOP_MEAS)
            os.system(f"./sw/jtag/run_elf.sh {elf_file} -c 'set ADAPTER_KHZ 4000'")
        else:
            raise ValueError(f"Interface {interface} is not yet supported")
        # wait untill chip writes to file
        # move to correct folder and parse output
    return 0


def move_to_datafolder(source_folder: Path, data_folder: Path, core: int):
    """
    Moves all the data in the source folder to the destination, taking into account for which core the data is meant.

    @type source_folder: Path
    @param source_folder: the source folder where all the data is stored.
    @type data_folder: Path
    @param data_folder: destination folder where the data will be copied.
    @type core: int
    @param core: which core the data is destined.
    """
    files = ["clusters", "states_in", "energy", "energy_best"]
    for run in range(2):
        for file in files:
            rename_move_file(source_folder / f"{file}_{run + 1}", data_folder, f"{file}_{2 * core + (run + 1)}")


def rename_move_file(source: Path, destination: Path, newname: str):
    """Performs the linux command:
    ```
    cp <source> <destination/newname>
    ```

    @type source: Path
    @param source: source path
    @type destination: Path
    @param destination: destination path
    @type newname: str
    @param newname: the new name of the file
    """
    os.system(f"cp {source} {destination / newname}")


def wait_for_chip():
    pass


if __name__ == "__main__":
    send_chip(TOP_MEAS / "openising/Maxcut_experiment/model_0", 2, 2)
