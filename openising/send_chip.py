import os
from pathlib import Path
from __init__ import current_dir
from sw.uart.send_uart import main

def send_chip(save_folder:Path, nb_runs, nb_cores: int):
    """_summary_

    Args:
        save_folder (str): _description_
    """
    assert nb_cores <= 2
    # copy data to folder
    datafolder = current_dir / "lagd-im/sw/tests/data/default"
    for run in range(0, nb_runs, nb_cores):
        folder_1 = save_folder / f"run_{run}"
        rename_move_file(folder_1 / "model", datafolder, "model_1")
        move_to_datafolder(folder_1, datafolder, 0)
        if nb_cores == 2:
            folder_2 = save_folder / f"run_{run+1}"
            move_to_datafolder(folder_2, datafolder, 1)
            rename_move_file(folder_2 / "model", "model_2")

        # run makefile
        lagd_folder = current_dir / "lagd-im"
        os.system(f"cd {lagd_folder}")
        os.system("pixi shell")
        elf_file = "lagd_commands.elf"
        if nb_cores == 1:
            os.system("CORE_TESTED=0 ./ci/sys-run.sh --binary=sw/tests/lagd_scompute.spm.elf")
            rename_move_file(lagd_folder / "sw/tests/lagd_scompute.spm.elf", folder_1, elf_file)
        else:
            os.system("./ci/sys-run.sh --binary=sw/tests/lagd_dcompute.spm.elf")
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_1, elf_file)

    # send to chip (send_uart)
    # wait untill chip writes to file
    # move to correct folder and parse output
    pass

def move_to_datafolder(source_folder:Path, data_folder:Path, core:int):
    files = ["clusters", "state_in", "energy", "energy_best"]
    for run in range(2):
        for file in files:
            rename_move_file(source_folder / f"{file}_{run+1}", data_folder, f"{file}_{2*core+(run+1)}")

def rename_move_file(source:Path, destination: Path, newname: str):
    os.system(f"mv {source} {destination / newname}")
