import os
import subprocess
import sys

from pathlib import Path
from __init__ import TOP_MEAS

def send_chip(save_folder:Path, nb_runs, nb_cores: int):
    """_summary_

    Args:
        save_folder (str): _description_
    """
    assert nb_cores <= 2
    lagd_folder = TOP_MEAS / "openising/lagd-im"
    os.chdir(lagd_folder)
    # copy data to folder
    datafolder = TOP_MEAS / "openising/lagd-im/sw/tests/data/default"
    for run in range(0, int(nb_runs / 2), nb_cores):
        folder_1 = save_folder / f"run_{run}"
        rename_move_file(folder_1 / "model", datafolder, "model_1")
        move_to_datafolder(folder_1, datafolder, 0)
        if nb_cores == 2 and (nb_runs % 4 == 0 or run != int(nb_runs/2-1)):
            folder_2 = save_folder / f"run_{run+1}"
            move_to_datafolder(folder_2, datafolder, 1)
            rename_move_file(folder_2 / "model", datafolder, "model_2")
        else:
            folder_2 = None

        # run makefile
        elf_file = "lagd_commands.elf"
        if folder_2 is not None:
            os.system("pixi run ./ci/sys-run.sh --binary=sw/tests/lagd_dcompute.spm.elf")
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_1, elf_file)
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_2, elf_file)
        else:
            os.system("pixi run bash -c 'CORE_TESTED=0 ./ci/sys-run.sh --binary=sw/tests/lagd_scompute.spm.elf'")
            rename_move_file(lagd_folder / "sw/tests/lagd_scompute.spm.elf", folder_1, elf_file)

        # send to chip (send_uart)
        send_uart_path = TOP_MEAS/ "sw/uart/send_uart.py"
        dev = "/dev/ttyUSB2"
        subprocess.run(
            [sys.executable, str(send_uart_path), str(folder_1 / elf_file),
             "--device", dev, "--no-rtscts", "--verify", "--run-timeout", "10"],
            timeout=30)

    # wait untill chip writes to file
    # move to correct folder and parse output
    pass

def move_to_datafolder(source_folder:Path, data_folder:Path, core:int):
    files = ["clusters", "states_in", "energy", "energy_best"]
    for run in range(2):
        for file in files:
            rename_move_file(source_folder / f"{file}{run+1}", data_folder, f"{file}_{2*core+(run+1)}")

def rename_move_file(source:Path, destination: Path, newname: str):
    os.system(f"cp {source} {destination / newname}")

if __name__ == "__main__":
    send_chip(TOP_MEAS / "openising/Maxcut_experiment/model_0", 2, 2)
