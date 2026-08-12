# OPENISING Experiment Generation

This folder holds all the scripts for generating and compiling the experiment data for the lagd chip. Generating data, compiling it and sending it to chip are all possible with the script `generate_experiment.py`. By tweaking some of the arguments data can be generated or send to the chip. The following arguments are available:

- `-config-file <path/to/config/folder>`: This configuration file will be loaded. Only the path to the folder must be given as the script will automatically append the file `config_experiment.yaml` to the path. The default setting is `openising/Maxcut_experiment/model_0`.
- `--logging-level <logging-level>`: the logging level for the software simulation. Defaults to INFO.
- `--simulate`: whether to simulate or send to chip. If this argument is present the software simulation will be run.
- `--nb-cores <nb-cores>`: The amount of on-chip cores that will be used. Only a value of 1 or 2 are possible. Defaults to 1.
- `--interface <interface>`: Important to set when `--simulate` is not present as this holds the interface with which to send the data to the chip. Defaults to `uart`.
- `--host <host>`: the ip of the measurement host, should be structured as user@ip. The default setting is `root@10.88.18.6`. It is best not to differ from the default setting.
- `-b <baud>` or `--baud <baud>`: the baud rate to send/receive data for the uart interface. It must match the chip which is set at 115200 baud.
- `-d <device>` or `--device <device>`: the device for the uart interface. Default setting is `/dev/ttyUSB2`.
- `--remote-dir <remote/directory>`: the directory on the remote host that is linked to your directory here. The default directory is `Workspace/workspace_sofie`.
- `--timeout <timeout>`: the allowed response time in seconds, needed for uart. Default set to 5 seconds.
- `--plot-sw`: if this argument is added for an MPPI experiment the software simulation will also be plotted.

# Postprocessing
Currently the file `postprocessing.py` holds a few functions with which plots can be made. These function can be used with the retrieved data from the on-chip experiments. The plotting functions are:

- `plot_convergence_run()`: Plots the best energy over one run. The resulting figure will plot the Hamiltonian energy over the iteration.
- `plot_BER()`: the BER over SNR plot. A list of data folders need to be given where the output is stored to ensure multiple SNR points are plotted.
- `plot_convergence_multi()`: similar to `plot_convergence_run()` but now all the runs are taken into account. The resulting figure will have a shaded std region and a full line for the mean value.
- `boxplot()`: This will make a boxplot of the final energies of every folder in the list of data folders that were given. The final energies are marked by their relative distance to the best found if it is known.
- `plot_mppi()`: This will plot the trajectories of the mpc experiment. This function is automatically called after the MPPI experiment.

Every function has the boolean argument `add_sw` that allows for the software simulation to also be plotted next to the hardware simulation.