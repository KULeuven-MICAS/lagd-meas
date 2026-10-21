# Result tests performed for ISSCC paper

This folder holds all the config files needed to generate the data that was used to make the figures in our ISSCC submission. The data of each figure can be found in its corresponding folder, e.g. for the pm1d_100 data with 50 iterations has the energy results in ./openising/ISSCC_tests/Maxcut_experiment/pm1d_100. In order to recreate the figure, you can run openising/postprocessing.py 

## Figure 5 down
### Maxcut data
The different maxcut benchmark names are:
    - pm1d_100, pm1d_100_1it
    - pm1s_100, pm1s_100_1it
    - pm1d_80, pm1d_80_1it
    - pm1s_80, pm1s_80_1it

**_1it refers to the 1 it/run experiments. A csv file with the final energies is stored, together with the boxplot in the pm1d_100(_1it) folders. 

### MPC experiment
All the different trajectories are stored in their corresponding csv files (reference, predicted and executed trajectory). The file ans_results.pkl holds same information.

## Figure 6 upper table, MIMO BER calculation

In the MIMO folder the predicted and sent symbols are stored in the corresponding csv file. The BER which is calculated from this data is stored in its corresponding file.
