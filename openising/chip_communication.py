# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import os
import subprocess
import numpy as np
import yaml
import csv

from pathlib import Path
from __init__ import (
    TOP_MEAS,
    TOP_LAGD_IM,
    connect_to_host_commands,
    default_remote_dir,
    default_host,
    default_device,
    remote_python,
)
from submodules.openising.ising.stages.simulation_stage import Ans
from openising.postprocessing import load_ans
from target.zcu102.top import (
    run_elf,
)
from sw.tests.smu_setup import setup_smu


def compile_data_convergence(data_folders: list[Path], nb_iteration: int, core: int):
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
    cases = ["_galena", ""]
    for folder in data_folders:
        move_to_datafolder(folder, compile_folder, core)

        for case in cases:
            rename_move_file(folder / f"model{case}", compile_folder, f"model_{core + 1}")
            for it in range(1, nb_iteration + 1):
                data[index] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(2 * it)} // max: 0x0400 (1024)\n"
                with Reg_file.open("w") as f:
                    f.writelines(data)

                elf_file = f"lagd_commands_iteration{it}{case}.elf"
                subprocess.run(
                    [
                        "pixi",
                        "run",
                        f"make -C ./sw clean all BENDER=bender VERIFICATION_TEST=0 CORE_TESTED={core} PROGRAM_GALENA={int(case == '_galena')}",
                    ]
                )
                rename_move_file(TOP_LAGD_IM / "sw/tests/lagd_scompute.spm.elf", folder, elf_file)


def compile_data(data_folders: list[Path], nb_cores: int, core: int):
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
    data[index] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(nb_flipping * 2)} // max: 0x0400 (1024)\n"
    with Reg_file.open("w") as f:
        f.writelines(data)

    cases = ["_galena", ""]
    for run in range(0, nb_runs, nb_cores):
        folder_1 = data_folders[run]
        move_to_datafolder(folder_1, compile_folder, core)
        for case in cases:
            rename_move_file(folder_1 / f"model{case}", compile_folder, f"model_{core + 1}")
            if nb_cores == 2 and run + 1 < nb_runs:
                folder_2 = data_folders[run + 1]
                move_to_datafolder(folder_2, compile_folder, 1)
                rename_move_file(folder_2 / f"model{case}", compile_folder, "model_2")
            else:
                folder_2 = None

            # run makefile
            elf_file = f"lagd_commands{case}.elf"
            subprocess.run(
                [
                    "pixi",
                    "run",
                    f"make -C ./sw clean all BENDER=bender VERIFICATION_TEST=0 CORE_TESTED={core} PROGRAM_GALENA={int(case == '_galena')}",
                ]
            )
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
    interface: str,
    elf_file: str,
    rtscts: bool = False,
):
    # ssh to xilinx first
    tokens = [
        remote_python,
        "-m",
        "openising.uart_output",
        "--device",
        device,
        "--baud",
        str(baud),
        "--timeout",
        str(timeout),
        "--no-rtscts" if not rtscts else "",
        "-interface",
        interface,
        "-elf",
        elf_file,
    ]
    subprocess.run(connect_to_host_commands + tokens, stdout=stdout, check=True)


def interface_send(
    interface: str, top_log: Path, host, remote_dir, elf_file, uart_device, rtscts, uart_baud, uart_timeout
):
    if interface == "uart":
        with top_log.open("w") as f:
            flags = ["--no-rtscts"] if not rtscts else []
            run_elf(host, remote_dir, elf_file, uart_device, flags, f)

    elif interface in ["spi", "jtag"]:
        with top_log.open("w") as f:
            _stream_uart_output(f, uart_device, uart_baud, uart_timeout, interface, elf_file, rtscts)
    else:
        raise ValueError(f"Interface {interface} is not yet supported")


def send_chip(
    data_folder: Path,
    interface: str,
    host: str,
    uart_device: str,
    uart_baud: int,
    uart_timeout: float,
    rtscts: bool,
    remote_dir: str,
    chip: int,
    core: int,
    smu_config_file: Path,
    nb_cores: int,
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
    if ans.config.problem_type == "MIMO":
        nb_variables = ans.MIMO[0].ising_model.num_variables
        nb_runs = min(ans.config.nb_trials, ans.config.dummy_case_num)
    else:
        nb_variables = ans.ising_model.num_variables
        nb_runs = int(ans.config.nb_runs / 2)
    prev_scalings = 1
    instruments, current_settings, smu_config = setup_smus(smu_config_file, chip, core)
    for run in range(0, nb_runs, nb_cores):
        prev_scalings = set_smus(instruments, ans, run, prev_scalings, current_settings, smu_config)
        # Reset board
        for case in ["_galena", ""]:
            top_log = TOP_MEAS / f"top{case}.log"
            subprocess.run(connect_to_host_commands + [f"{remote_python} sw/tests/chip_test.py"])
            run_folder = data_folder / f"run_{run}"
            elf_file = str((run_folder / f"lagd_commands{case}.elf").relative_to(TOP_MEAS))
            interface_send(interface, top_log, host, remote_dir, elf_file, uart_device, rtscts, uart_baud, uart_timeout)
            # move to correct folder and parse output
        folders = [run_folder]
        if nb_cores == 2:
            folders.append(data_folder / f"run_{run + 1}")
        retrieve_data_from_output(folders, nb_cores, nb_variables, nb_flipping, ans.ising_model)
    return 0


def send_chip_convergence(
    data_folder: Path,
    interface: str,
    host: str,
    uart_device: str,
    uart_baud: int,
    uart_timeout: float,
    remote_dir: str,
    chip: int,
    core: int,
    smu_config_file: Path,
    rtscts: bool,
):

    ans: Ans = load_ans(data_folder)
    nb_iterations = ans.config.nb_flipping
    if ans.config.problem_type in ["Maxcut", "MPPI"]:
        nb_runs = int(ans.config.nb_runs / 2)
    elif ans.config.problem_type == "MIMO":
        nb_runs = int(ans.config.nb_trials)

    prev_scalings = 1
    instruments, current_settings, smu_config = setup_smus(smu_config_file, chip, core)

    for run in range(nb_runs):
        run_folder = data_folder / f"run_{run}"
        prev_scalings = set_smus(instruments, ans, run, prev_scalings, current_settings, smu_config)

        for it in range(1, nb_iterations + 1):
            print(f"iteration: {it}")
            for case in ["_galena", ""]:
                top_log = TOP_MEAS / f"top{case}.log"
                subprocess.run(connect_to_host_commands + [f"{remote_python} sw/tests/chip_test.py"])
                elf_file = str((run_folder / f"lagd_commands_iteration{it}{case}.elf").relative_to(TOP_MEAS))
                interface_send(
                    interface, top_log, host, remote_dir, elf_file, uart_device, rtscts, uart_baud, uart_timeout
                )
            # move to correct folder and parse output
            retrieve_data_from_output([run_folder], 1, ans.ising_model.num_variables, it, ans.ising_model, True)

def setup_smus(smu_config_file:Path, chip: int, core: int):
    with smu_config_file.open("r") as f:
        smu_cfg_all = yaml.safe_load(f)

    smu_config = smu_cfg_all["source_measure_units"]
    instruments = dict()
    for smu in smu_config.keys():
        instruments[smu] = setup_smu(smu, True, "current", smu_config_file)

    settings_file = TOP_MEAS / f"openising/calibration_currents/currents_chip{chip}_core{core}.csv"

    current_settings = None
    with settings_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                if float(row.get("base", "nan")) == smu_config["smu_1"]["current"]:
                    current_settings = row
                    break
            except ValueError:
                continue

    if current_settings is None:
        raise ValueError(f"No calibration done for {smu_config['smu_1']['current']}")

    for smu, instrument in instruments.items():
        if smu == "smu_1":
            instrument.set_current_source(smu_config[smu]["current"], smu_config[smu]["voltage_limit"])
        else:
            mode = smu_config[smu]["calibration_mode"]
            key = mode + "_sf1" if "h" in mode else mode
            instrument.set_current_source(float(current_settings[key]), smu_config[smu]["voltage_limit"])
    return instruments, current_settings, smu_config

def set_smus(
    instruments: list, ans: Ans, run: int, prev_scalings: list[int], current_settings: dict[str:float], smu_config: dict
):
    if ans.config.problem_type == "MIMO":
        scaling_factors = ans.MIMO[run + 1].h_scale_factor
    else:
        scaling_factors = ans.h_scale_factor
    if scaling_factors != prev_scalings:
        instruments["smu_3"].set_current_source(
            float(current_settings[smu_config["smu_3"]["calibration_mode"] + f"_sf{scaling_factors}"])
        )
        instruments["smu_4"].set_current_source(
            float(current_settings[smu_config["smu_4"]["calibration_mode"] + f"_sf{scaling_factors}"])
        )
    return scaling_factors


def retrieve_data_from_output(
    data_folders: list[Path],
    nb_cores: int,
    nb_variables: int,
    nb_flipping: int,
    ising_model,
    convergence_mode: bool = False,
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
                    if nb_cores == 1:
                        curr_core = 0
                    else:
                        curr_core = int(parts_line[4][0])
                    run = (int(parts_line[-2]) - 1) % 2
                    iteration = int((int(parts_line[-2]) - 1) / 2)
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    cur_run = 2 * curr_core + run
                    energies[cur_run, iteration] = energy
                    if iteration > current_it[cur_run]:
                        energies[cur_run, current_it[cur_run] : iteration] = energies[cur_run, current_it[cur_run]]
                    if np.all(energies[cur_run, :iteration] == np.zeros_like(energies[cur_run, :iteration])):
                        # account for the case the first iteration is not zero
                        energies[cur_run, :iteration] = energy
                    current_it[cur_run] = iteration
                elif "spin_fifo_data" in line:
                    # spin case
                    state = bin(int(parts_line[-1], 16))[2:].zfill(256)
                    if nb_cores == 1:
                        curr_core = 0
                    else:
                        curr_core = int(parts_line[1][-3])
                    run = int(parts_line[1][-5])
                    for node in range(nb_variables):
                        final_states[curr_core * 2 + run][node] = int(state[node]) * 2 - 1
                    print(
                        f"Ising energy: {ising_model.evaluate(final_states[curr_core * 2 + run])},\
 State: {final_states[curr_core * 2 + run, 0 : ising_model.num_variables]}"
                    )
                elif "Energy FIFO data" in line:
                    # final energy case
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    if nb_cores == 1:
                        curr_core = 0
                    else:
                        curr_core = int(parts_line[-2][0])
                    run = int(parts_line[4])
                    cur_run = 2 * curr_core + run
                    if current_it[cur_run] < nb_flipping - 1:
                        energies[cur_run, current_it[cur_run] + 1 :] = energy
                    else:
                        energies[cur_run, -1] = energy
    if not convergence_mode:
        for core, folder in zip(range(nb_cores), data_folders):
            for run in range(2):
                np.savetxt(folder / f"hw_best_energy_{run + 1}", energies[2 * core + run, :])
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
                    print(best_energies)
                    np.savetxt(folder / f"hw_best_energy_{run + 1}_convergence", best_energies, fmt="%32s")


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
        host=default_host,
        uart_baud=115200,
        uart_device=default_device,
        remote_dir=default_remote_dir,
    )
