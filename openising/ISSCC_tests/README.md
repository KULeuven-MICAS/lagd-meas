# Result tests performed for ISSCC paper

This folder holds all the config files needed to generate the data that was used to make the figures in our ISSCC submission. 

## Figure 5 down
The data of the left figure can be obtained by running:
```bash
python openising/generate_experiment.py -config-file openising/ISSCC_tests/Maxcut_experiment/<benchmark_name> --simulate && python openising/generate_experiment.py -config-file openising/ISSCC_tests/Maxcut_experiment/<benchmark_name>
```
The different benchmark names are:
    - pm1d_100, pm1d_100_1it
    - pm1s_100, pm1s_100_1it
    - pm1d_80, pm1d_80_1it
    - pm1s_80, pm1s_80_1it

The data of the right figure can be obtained by running:
```bash
python openising/generate_experiment.py -config-file openising/ISSCC_tests/MPPI_experiment/model_0
```

## Figure 6 upper table
The data of this table can be obtained by running:
```bash
python openising/generate_experiment.py -config-file openising/ISSCC_tests/MIMO_experiment/model_6 --simulate && python openising/generate_experiment.py -config-file openising/ISSCC_tests/MIMO_experiment/model_6
```
