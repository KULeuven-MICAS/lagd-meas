import os
import subprocess
import threading
import numpy as np
import shlex

from pathlib import Path
from __init__ import TOP_MEAS
from ising.stages.simulation_stage import Ans
from openising.postprocessing import load_ans
from target.zcu102.zcu102_reload import reload_board
from target.zcu102.top import run_elf, REMOTE_PYTHON, DEFAULT_REMOTE_DIR

DEFAULT_UART_DEVICE = "/dev/ttyUSB2"
DEFAULT_UART_BAUD = 115200


def compile_data_convergence(data_folder: Path, interface: str, nb_iteration: int):
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
    it_line = 72  # line 73 but start from 0
    for it in range(nb_iteration):
        with Reg_file.open("r") as f:
            data = f.readlines()
        data[it_line] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(it+1)} // max: 0x0400 (1024)"
        with Reg_file.open("w") as f:
            f.writelines(data)

        elf_file = f"lagd_commands_iteration{it}"
        subprocess.run(["pixi", "run", "make -C ./sw clean all BENDER=bender"])
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

    # make sure the amount of iterations is altered
    ans = Ans()
    ans.load(data_folders[0].parent / "ans.pkl")
    nb_flipping = ans.config.nb_flipping
    Reg_file = TOP_MEAS / "openising/lagd-im/sw/include/lagd_reg_params.h"
    it_line = 74  # line 73 but start from 0
    with Reg_file.open("r") as f:
        data = f.readlines()
    data[it_line] = f"#define ICON_LAST_RADDR_PLUS_ONE {hex(nb_flipping+1)} // max: 0x0400 (1024)\n"
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
        subprocess.run(["pixi", "run", "make -C ./sw clean all BENDER=bender"])
        if folder_2 is not None:
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_1, elf_file)
            rename_move_file(lagd_folder / "sw/tests/lagd_dcompute.spm.elf", folder_2, elf_file)
        else:
            rename_move_file(lagd_folder / "sw/tests/lagd_scompute.spm.elf", folder_1, elf_file)


def _stream_uart_output(stdout, device: str, baud: int, timeout: float, remote_dir, host, rtscts: bool = False, ):
    # ssh to xilinx first
    tokens = [
            REMOTE_PYTHON, "-m", "openising.uart_output",
            "--device", device,
            "--baud", str(baud),
            "--timeout", str(timeout),
            "--rtscts" if rtscts else ""
        ]
    remote_cmd = f"cd {shlex.quote(remote_dir)}/ && " + " ".join(shlex.quote(t) for t in tokens)
    subprocess.run(["ssh", "-t", host, remote_cmd], stdout=stdout, check=True)


def _start_uart_stream(
    stdout: Path,
    device: str,
    baud: int,
    timeout: float,
    host: str,
    remote_dir: str = DEFAULT_REMOTE_DIR,
    rtscts: bool = False,
) -> threading.Thread:
    thread = threading.Thread(
        target=_stream_uart_output,
        args=(stdout, device, baud, timeout, remote_dir, host, rtscts),
        daemon=True,
    )
    thread.start()
    return thread


def send_chip(
    data_folder: Path,
    nb_cores: int,
    interface: str,
    host: str = "root@10.88.18.26",
    uart_device: str = DEFAULT_UART_DEVICE,
    uart_baud: int = DEFAULT_UART_BAUD,
    uart_timeout: float = 3600.0,

) -> int:
    """Send the data of the different software runs to the chip and wait untill the results from the chip are written\
       to a file.

    @type data_folder: pathlib.Path
    @param data_folder: the top folder where the data of all the runs and elf files are stored.
    @type nb_cores: int
    @param nb_cores: the amount of cores that will be used on chip
    @type send_to_chip: bool
    @param send_to_chip: whether the chip is being used or not.
    @type interface: str
    @param interface: the interface used to send the data to chip. Currently supports `jtag` and `uart`.
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
        nb_runs = int(ans.config.nb_runs/2)
    # set up stream
    reload_board()
    # setup for jtag and spi: 1. reload board, 2. open uart port to wait, 3. run elf file, 4. read from uart port
    for run in range(0, nb_runs, nb_cores):
        run_folder = data_folder / f"run_{run}"
        elf_file = (run_folder / "lagd_commands.elf").relative_to(TOP_MEAS)
        # reload chip
        # send to chip (send_uart)
        if interface == "uart":
            with top_log.open("w") as f:
                run_elf(host, "Workspace/workspace_sofie", str(elf_file), uart_device, ["--no-rtscts"], f)

        elif interface == "jtag":
            with top_log.open("w") as f:
                uart_thread = _start_uart_stream(f, uart_device, uart_baud, uart_timeout, host)
                subprocess.run(
                    ["ssh", host, "Workspace/workspace_sofie/sw/jtag/run_elf.sh", f"{elf_file}", "-c", "set ADAPTER_KHZ 4000"],
                    cwd=TOP_MEAS,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            uart_thread.join(timeout=uart_timeout)
            if uart_thread.is_alive():
                raise TimeoutError("timed out waiting for UART output after JTAG launch")
        elif interface == "spi":
            with top_log.open("w") as f:
                uart_thread = _start_uart_stream(f, uart_device, uart_baud, uart_timeout, host)
                subprocess.run(
                    ["ssh", host, "python", "Workspace/workspace_sofie/sw/tools/spi_program_loader.py", f"{elf_file}"],
                    cwd=TOP_MEAS,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            uart_thread.join(timeout=uart_timeout)
            if uart_thread.is_alive():
                raise TimeoutError("timed out waiting for UART output after SPI launch")
        else:
            raise ValueError(f"Interface {interface} is not yet supported")
        # move to correct folder and parse output
        if nb_cores == 2:
            folders = [run_folder, data_folder / f"run_{run+1}"]
        else:
            folders = [run_folder]
        retrieve_data_from_output(folders, nb_cores, nb_variables, nb_flipping)
    return 0

def retrieve_data_from_output(data_folders: list[Path], nb_cores:int, nb_variables: int, nb_flipping: int):
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
    """
    output_file = TOP_MEAS / "top.log"
    energies = np.zeros((2*nb_cores, nb_flipping))
    final_states = np.zeros((2*nb_cores, nb_variables), dtype=int)
    current_it = np.zeros((2*nb_cores,), dtype=int)
    with output_file.open("r") as f:
        for line in f.readlines():
            parts_line = line.split(" ")
            if parts_line[0] == "[chip]":
                if "energy_fifo_data" in line:
                    # energy case
                    core = int(parts_line[4][0])
                    run = (int(parts_line[-2])-1) % 2
                    iteration = int((int(parts_line[-2])-1)/2)
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    cur_run = 2*core + run
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
                        final_states[core*2 + run][node] = int(state[node])*2-1
                else:
                    #final energy case
                    energy = int.from_bytes(bytes.fromhex(parts_line[-1][2:]), signed=True)
                    core = int(parts_line[-2][0])
                    run = int(parts_line[4])
                    cur_run = 2*core + run
                    energies[cur_run, current_it[cur_run]+1:] = energy
    for core, folder in zip(range(nb_cores), data_folders):
        for run in range(2):
            np.savetxt(folder/f"hw_best_energy_{run+1}", energies[2*core + run, :],fmt="%32s")
            np.savetxt(folder/f"hw_final_state_{run+1}", final_states[2*core+run, :], fmt="%1u")


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
    send_chip(TOP_MEAS / "openising/Maxcut_experiment/model_0", 2, "spi")
