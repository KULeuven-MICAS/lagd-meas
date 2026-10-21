# Result tests performed for ISSCC paper

This folder holds all the config files and measurement data that was used to make the figures in our ISSCC submission. The data of each figure can be found in its corresponding folder, e.g. for the pm1d_100 data with 50 iterations has the energy results in ./openising/ISSCC_tests/Maxcut_experiment/pm1d_100. In order to recreate the figure, you can run openising/postprocessing.py 

## Figure 5
### Maxcut data
Under the folder openising/ISSCC_tests/Maxcut_experiment there are 8 folders with the data of maxcut experiments, seen in figure 5 bottom left. The four different benchmarks pm1d_100, pm1d_80, pm1s_100, and pm1s_80 are run for 50 iterations or 1 iterations (stored with the suffix _1it) and the resulting energies are stored in maxcut_raw_energies_deltah.csv. These energies are used to create the figures for the 50 iteration per run (see openising/ISSCC_tests/Maxcut_experiment/boxplot.svg) or 1 iteration per run (see openising/ISSCC_tests/Maxcut_experiment/boxplot_1it.svg).

### MPC experiment
The data of this experiment is shown in figure 5 bottom right.
Under the folder openising/ISSCC_tests/MPC_experiment/model_0 the following files are there:
 - ans_result.pkl: holds all the information of the scene and result data of the problem. However this file is not human-readable
 - executed_trajectory.csv: the trajectory that was executed by the `robot' bycicle. This one should follow the reference trajectory as closely as possible. It is represented by the dark-green line in the figure.
 - predicted_trajectory.csv: the trajectory that is predicted of horizon length N at every iteration. Only the first step is executed and results in the executed trajectory. It is represented by the light-green lines in the figure.
 - reference_trajectory.csv: the trajectory that the `robot' bycicle should follow. It is represented by the dark blue line in the figure.
 - mppi_results.svg: the resulting figure which is used for the ISSCC paper.
 - config_experiment.yaml: the settings used to generate the data.

## Figure 6 upper table, MIMO BER calculation
Under the folder openising/ISSCC_tests/MIMO_experiment/model_6 there are the following files:
 - ber_deltah.csv: the resulting BER that is reported in the table
 - symbols_deltah.csv: the send and predicted symbols of all the 24 users over all the 1000 runs. This is used to compute the BER.
 - ans.pkl: this file holds all the information about the send symbols. However, the file is not human-readable.
 - config_experiment.yaml: the settings used to generate the experiment data.
