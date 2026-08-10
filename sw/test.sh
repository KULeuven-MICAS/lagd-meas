#!/bin/bash

for i in $(seq 1 100); do
    echo "=== Run $i/100 ==="
    ./target/zcu102/zcu102_reload.py
    ssh root@10.88.18.26 "cd Workspace/workspace_sofie/ && source env.sh && python sw/tests/chip_test.py"
done