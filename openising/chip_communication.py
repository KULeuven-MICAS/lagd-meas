# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import os
import subprocess
import numpy as np
import shlex

from pathlib import Path
from __init__ import TOP_MEAS, TOP_LAGD_IM
from submodules.openising.ising.stages.simulation_stage import Ans
from openising.postprocessing import load_ans
from target.zcu102.zcu102_reload import reload_board
from target.zcu102.top import (
    run_elf,
    REMOTE_PYTHON,
    DEFAULT_DEVICE,
    DEFAULT_HOST,
    DEFAULT_REMOTE_DIR,
)


def compile_data_convergence(data_folders: list[Path], nb_iteration: int):
    """Compiles data for every flipping iteration of one run.

    @type data_folders: list[pathlib.Path]
    @param data_folders: list of folders where the data is stored
    @type interface: str
    @param interface: what interface to use to send the data
    @type nb_iteration: int
    @param nb_iteration: the amount of flipping iterations
    """
    os.chdir(TOP_LAGD_IM)
    compile_folder = TOP_LAGD_IM / "sw/tests/data/default"
    Reg_file = TOP_LAGD_IM / "sw/include/lagd_reg_params.h"
    with Reg_file.open("r") as f:
        data = f.readlines()
        for line in data:
            if line.find("#define ICON_LAST_RADDR_PLUS_ONE") != -1:
                index = data.index(line)
    for folder in data_folders:
        rename_move_file(folder / "model", compile_folder, "model_1")
        move_to_datafolder(folder, compile_folder, 0)

        for it in range(1, nb_iteration + 1):
            data[index] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(it)} // max: 0x0400 (1024)\n"
            with Reg_file.open("w") as f:
                f.writelines(data)

            elf_file = f"lagd_commands_iteration{it}.elf"
            subprocess.run(["pixi", "run", "make -C ./sw clean all BENDER=bender VERIFICATION_TEST=0"])
            rename_move_file(TOP_LAGD_IM / "sw/tests/lagd_scompute.spm.elf", folder, elf_file)


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
    os.chdir(TOP_LAGD_IM)
    # copy data to folder
    compile_folder = TOP_LAGD_IM / "sw/tests/data/default"
    nb_runs = len(data_folders)

    # make sure the amount of iterations is altered
    ans = Ans()
    ans.load(data_folders[0].parent / "ans.pkl")
    nb_flipping = ans.config.nb_flipping
    Reg_file = TOP_LAGD_IM / "sw/include/lagd_reg_params.h"
    with Reg_file.open("r") as f:
        data = f.readlines()
        for line in data:
            if line.find("#define ICON_LAST_RADDR_PLUS_ONE") != -1:
                index = data.index(line)
    data[index] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(nb_flipping + 1)} // max: 0x0400 (1024)\n"
    with Reg_file.open("w") as f:
        f.writelines(data)

    for run in range(0, nb_runs, nb_cores):
        folder_1 = data_folders[run]
        rename_move_file(folder_1 / "model", compile_folder, "model_1")
        move_to_datafolder(folder_1, compile_folder, 0)
        if nb_cores == 2 and run + 1 < nb_runs:
            folder_2 = data_folders[run + 1]
            move_to_datafolder(folder_2, compile_folder, 1)
            rename_move_file(folder_2 / "model", compile_folder, "model_2")
        else:
            folder_2 = None

        # run makefile
        elf_file = "lagd_commands.elf"
        subprocess.run(["pixi", "run", "make -C ./sw clean all BENDER=bender VERIFICATION_TEST=0"])
        if folder_2 is not None:
            rename_move_file(TOP_LAGD_IM / "sw/tests/lagd_dcompute.spm.elf", folder_1, elf_file)
            rename_move_file(TOP_LAGD_IM / "sw/tests/lagd_dcompute.spm.elf", folder_2, elf_file)
        else:
            rename_move_file(TOP_LAGD_IM / "sw/tests/lagd_scompute.spm.elf", folder_1, elf_file)


def _stream_uart_output(
    stdout,
    device: str,
    baud: int,
    timeout: float,
    remote_dir,
    host,
    interface: str,
    elf_file: str,
    rtscts: bool = False,
):
    # ssh to xilinx first
    tokens = [
        f"cd {shlex.quote(remote_dir)}/ && ",
        "source",
        "env.sh",
        "&&",
        REMOTE_PYTHON,
        "-m",
        "openising.uart_output",
        "--device",
        device,
        "--baud",
        str(baud),
        "--timeout",
        str(timeout),
        "--rtscts" if rtscts else "",
        "-interface",
        interface,
        "-elf",
        elf_file,
    ]
    subprocess.run(["ssh", "-t", host] + tokens, stdout=stdout, check=True)


def send_chip(
    data_folder: Path,
    nb_cores: int,
    interface: str,
    host: str,
    uart_device: str,
    uart_baud: int,
    uart_timeout: float,
    rtscts: bool,
    remote_dir: str,
) -> int:
    """Send the data of the different software runs to the chip and wait untill the results from the chip are written\
       to a file.

    @type data_folder: pathlib.Path
    @param data_folder: the top folder where the data of all the runs and elf files are stored.
    @type nb_cores: int
    @param nb_cores: the amount of cores that will be used on chip
    @type interface: str
    @param interface: the interface used to send the data to chip. Currently supports `jtag`, `spi`, and `uart`.
    @type host: str
    @param host: the ip of the board.
    @type uart_device: str
    @param uart_device: the device used on the board which holds the uart connection.
    @type uart_baud: int
    @param uart_baud: baud rate for uart.
    @type uart_timeout: float
    @param uart_timeout: amount of time to wait for uart.
    @type remote_dir: str
    @param remote_dir: the directory on the board in which everything is stored.
    @rtype: int
    @return: return message for whether everything has finished correctly.
    """
    ans = load_ans(data_folder)
    nb_flipping = ans.config.nb_flipping
    top_log = TOP_MEAS / "top.log"
    if ans.config.problem_type == "MIMO":
        nb_variables = ans.MIMO[0].ising_model.num_variables
        nb_runs = min(ans.config.nb_trials, ans.config.dummy_case_num)
    else:
        nb_variables = ans.ising_model.num_variables
        nb_runs = int(ans.config.nb_runs / 2)
    prev_scalings = [1, 1]
    scaling_factors = [1, 1]
    for run in range(0, nb_runs, nb_cores):
        for i in range(nb_cores):
            if ans.config.problem_type == "MIMO":
                scaling_factors[i] = ans.MIMO[run+1].h_scale_factor
            else:
                scaling_factors[i] = ans.h_scale_factor
        print(f"scaling factors: {scaling_factors}")
        for i in range(nb_cores):
            if scaling_factors[i] != prev_scalings[i]:
                print(f"Need to recalibrate core {i}")
                breakpoint()
        prev_scalings = scaling_factors
        reload_board()
        run_folder = data_folder / f"run_{run}"
        elf_file = str((run_folder / "lagd_commands.elf").relative_to(TOP_MEAS))
        if interface == "uart":
            with top_log.open("w") as f:
                run_elf(host, remote_dir, elf_file, uart_device, ["--no-rtscts" if not rtscts else ""], f)

        elif interface in ["spi", "jtag"]:
            with top_log.open("w") as f:
                _stream_uart_output(
                    f, uart_device, uart_baud, uart_timeout, remote_dir, host, interface, elf_file, rtscts
                )
        else:
            raise ValueError(f"Interface {interface} is not yet supported")
        # move to correct folder and parse output
        if nb_cores == 2:
            folders = [run_folder, data_folder / f"run_{run + 1}"]
        else:
            folders = [run_folder]
        retrieve_data_from_output(folders, nb_cores, nb_variables, nb_flipping)
    return 0


def send_chip_convergence(
    data_folder: Path,
    interface: str,
    host: str,
    uart_device: str,
    uart_baud: int,
    uart_timeout: float,
    remote_dir: str,
):

    ans: Ans = load_ans(data_folder)
    nb_iterations = ans.config.nb_flipping
    if ans.config.problem_type in ["Maxcut", "MPPI"]:
        nb_runs = int(ans.config.nb_runs / 2)
    elif ans.config.problem_type == "MIMO":
        nb_runs = int(ans.config.nb_trials)
    top_log = TOP_MEAS / "top.log"
    for run in range(nb_runs):
        run_folder = data_folder / f"run_{run}"
        for it in range(1, nb_iterations + 1):
            reload_board()
            elf_file = str((run_folder / f"lagd_commands_iteration{it}.elf").relative_to(TOP_MEAS))
            if interface == "uart":
                with top_log.open("w") as f:
                    run_elf(host, remote_dir, elf_file, uart_device, ["--no-rtscts"], f)

            elif interface in ["spi", "jtag"]:
                with top_log.open("w") as f:
                    _stream_uart_output(f, uart_device, uart_baud, uart_timeout, remote_dir, host, interface, elf_file)
            else:
                raise ValueError(f"Interface {interface} is not yet supported")
            # move to correct folder and parse output
            retrieve_data_from_output([run_folder], 1, ans.ising_model.num_variables, it, True)


def retrieve_data_from_output(
    data_folders: list[Path], nb_cores: int, nb_variables: int, nb_flipping: int, convergence_mode: bool = False
):
    """
    This function retrieves the output data of the chip and stores it in the correct folder.

    @type data_folders: list[Path]
    @param data_folders: a list of folders where to store the output data.
    @type nb_cores: int
    @param nb_cores: the amount of cores used on chip
    @type nb_variables: int
    @param nb_variables: the amount of variables of the model
    @type nb_flipping: int
    @param nb_flipping: the amount of flipping iterations. This ensures only this amount of energy values are stored.
    @type convergence_mode: bool
    @param convergence_mode: whether to append to the energy
    """
    output_file = TOP_MEAS / "top.log"
    energies = np.zeros((2 * nb_cores, nb_flipping))
    final_states = np.zeros((2 * nb_cores, nb_variables), dtype=int)
    current_it = np.zeros((2 * nb_cores,), dtype=int)
    with output_file.open("r") as f:
        for line in f.readlines():
            parts_line = line.split(" ")
            if parts_line[0] == "[chip]":
                if "energy_fifo_data" in line:
                    # energy case
                    core = int(parts_line[4][0])
                    run = (int(parts_line[-2]) - 1) % 2
                    iteration = int((int(parts_line[-2]) - 1) / 2)
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    cur_run = 2 * core + run
                    energies[cur_run, iteration] = energy
                    if iteration > current_it[cur_run]:
                        energies[cur_run, current_it[cur_run] : iteration] = energies[cur_run, current_it[cur_run]]
                    if np.all(energies[cur_run, :iteration] == np.zeros_like(energies[cur_run, :iteration])):
                        # account for the case the first iteration is not zero
                        energies[cur_run, :iteration] = energy
                    current_it[cur_run] = iteration
                elif "spin_fifo_data" in line:
                    # spin case
                    state = bin(int(parts_line[-1], 16))[2:].zfill(nb_variables)
                    core = int(parts_line[1][-3])
                    run = int(parts_line[1][-5])
                    for node in range(nb_variables):
                        final_states[core * 2 + run][node] = int(state[node]) * 2 - 1
                elif "Energy FIFO data" in line:
                    # final energy case
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    core = int(parts_line[-2][0])
                    run = int(parts_line[4])
                    cur_run = 2 * core + run
                    energies[cur_run, current_it[cur_run] + 1 :] = energy
    if not convergence_mode:
        for core, folder in zip(range(nb_cores), data_folders):
            for run in range(2):
                np.savetxt(folder / f"hw_best_energy_{run + 1}", energies[2 * core + run, :], fmt="%32s")
                np.savetxt(folder / f"hw_final_state_{run + 1}", final_states[2 * core + run, :], fmt="%1u")
    else:
        if nb_flipping == 1:
            for core, folder in zip(range(nb_cores), data_folders):
                for run in range(2):
                    np.savetxt(
                        folder / f"hw_best_energy_{run + 1}_convergence", energies[2 * core + run, :], fmt="%32s"
                    )
                    np.savetxt(
                        folder / f"hw_final_state_{run + 1}_convergence", final_states[2 * core + run, :], fmt="%1u"
                    )
        else:
            for core, folder in zip(range(nb_cores), data_folders):
                for run in range(2):
                    np.savetxt(
                        folder / f"hw_final_state_{run + 1}_convergence", final_states[2 * core + run, :], fmt="%1u"
                    )
                    best_energies = np.loadtxt(folder / f"hw_best_energy_{run + 1}_convergence")
                    best_energies = np.append(best_energies, energies[2 * core + run, -1])
                    np.savetxt(folder / f"hw_best_energy_{run + 1}", best_energies, fmt="%32s")


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
    subprocess.run(["cp", source, destination / newname])


if __name__ == "__main__":
    send_chip(
        TOP_MEAS / "openising/Maxcut_experiment/model_0",
        2,
        "spi",
        uart_timeout=10,
        host=DEFAULT_HOST,
        uart_baud=115200,
        uart_device=DEFAULT_DEVICE,
        remote_dir=DEFAULT_REMOTE_DIR,
    )
