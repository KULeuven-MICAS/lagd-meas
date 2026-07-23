from pathlib import Path
import numpy as np

from ising.utils.HDF5Logger import return_data
from ising.stages.model import IsingModel
from ising.stages.simulation_stage import Ans


def store_run(ans: Ans, save_folder: Path, problem_type: str) -> None:
    """Save the model and solver parameters in binary format.
    @type ans: Ans
    @param ans: return ans of the run
    @type save_folder: str
    @param save_folder: folder in which to save the results
    """
    if problem_type == "MIMO":
        nb_runs = min(ans.config.dummy_case_num, ans.config.nb_trials) * 2
    elif problem_type == "MPPI":
        nb_runs = 1
    else:
        nb_runs = ans.config.nb_runs
    save_folders = []
    for i in range(0, nb_runs, 2):
        if problem_type == "MIMO":
            logfile_1 = ans.MIMO[int(i / 2)].logfiles[0]
            logfile_2 = ans.MIMO[int(i / 2)].logfiles[1]
            scale_factor = ans.MIMO[int(i / 2)].h_scale_factor
        elif problem_type == "MPPI":
            logfile_1 = ans.MPPI[0].logfiles[0]
            logfile_2 = ans.MPPI[0].logfiles[0]
            scale_factor = ans.h_scale_factor
        else:
            logfile_1 = ans.logfiles[i]
            logfile_2 = ans.logfiles[i + 1]
            scale_factor = ans.h_scale_factor
        folder_run = save_folder / f"run_{int(i / 2)}"
        save_folders.append(folder_run)
        Path.mkdir(folder_run, exist_ok=True)
        data_names = ["cluster", "state_in", "energy_best", "energy"]
        for num, logfile in enumerate([logfile_1, logfile_2]):
            for data_name in data_names:
                store_results_logfile(
                    logfile,
                    data_name,
                    folder_run,
                    data_name + f"_{num + 1}"
                    if data_name not in ["state_in", "cluster"]
                    else "states_in" + f"_{num + 1}"
                    if data_name != "cluster"
                    else "clusters" + f"_{num + 1}",
                )
        if problem_type == "MIMO":
            quantized_model: IsingModel = ans.MIMO[int(i/2)].quantized_model
        else:
            quantized_model: IsingModel = ans.quantized_model
        quantized_model_J = np.zeros_like(quantized_model.J, dtype="<U4")
        quantized_model_h = np.zeros_like(quantized_model.h, dtype="<U4")
        for j in range(quantized_model.num_variables):
            quantized_model_h[j] = np.binary_repr(int(quantized_model.h[j]), width=4)
            for k in range(j, quantized_model.num_variables):
                quantized_model_J[j, k] = np.binary_repr(int(quantized_model.J[j, k]), width=4)
                quantized_model_J[k, j] = quantized_model_J[j, k]

        with (folder_run / "model").open("w") as f:
            f.write("# J matrix\n")
            np.savetxt(f, quantized_model_J, fmt="%4s")
            f.write("# h vector\n")
            np.savetxt(f, quantized_model_h, fmt="%4s")
            f.write(f"# offset\n{quantized_model.c}\n")
            f.write(f"# scaling factor h \n {scale_factor}\n")
    return save_folders


def store_results_logfile(logfile: Path, data_name: str, save_folder: Path, file_name: str) -> None:
    """Loads and stores the data from the given logfile

    @type logfile: pathlib.Path
    @param logfile: the logfile from where to retrieve the data
    @type data_name: str
    @param data_name: name of the data that will be retrieved.
    @type save_folder: pathlib.Path
    @param save_folder: folder where to save the data
    @type file_name: str
    @param file_name: name of the file to save.
    """
    data = return_data(logfile, data=data_name)
    save_path = save_folder / file_name

    if data_name == "energy" or data_name == "energy_best":
        new_data = np.zeros_like(data, dtype="<U32")
        for i in range(data.shape[0]):
            if data[i] != np.inf:
                new_data[i] = np.binary_repr(round(data[i]), width=32)
        if data.shape[0] < 513:
            padding = np.full((513 - data.shape[0],), new_data[-1])
            new_data = np.append(new_data, padding)
        with save_path.open("w") as f:
            np.savetxt(f, new_data, fmt="%32s", delimiter="")
        return
    elif data_name == "state_in":
        new_data = np.where(data <= 0, 0, 1)
    else:
        new_data = data
        if data.shape[0] < 513:
            padding = np.full((513 - data.shape[0], data.shape[1]), 0)
            new_data = np.append(new_data, padding, axis=0)
    with save_path.open("w") as f:
        np.savetxt(f, new_data, fmt="%1u", delimiter="")
