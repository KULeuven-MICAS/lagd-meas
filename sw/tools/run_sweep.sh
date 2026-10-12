#!/usr/bin/env bash
# Sweep start states by running one ELF per state, instead of looping inside one ELF.
#
# Each state needs its own build: the start state is baked into the data folder, and a second
# capture burst inside one program does not refresh the capture memory. So this builds N ELFs,
# keeps them side by side under experiments/<problem>/sweep/elf/, then runs them one at a time.
#
# Prepare the data folders first:
#     problem = load_model("pm1d_100", magnitude=3)
#     emit_sweep(problem, "sweep", 20, seed=1)        # -> sweep_000 .. sweep_019
#     uv run --python 3.14 --with numpy sw/tools/gen_ising_problem.py
#
# Then:
#     sw/tools/run_sweep.sh              # build all, then run all
#     sw/tools/run_sweep.sh --build      # build only
#     sw/tools/run_sweep.sh --run        # run only, using what is already built
set -euo pipefail

# --- what to sweep -----------------------------------------------------------
PROBLEM=pm1d_80_0
PREFIX=pm1d_80_0
COUNT=10                       # matches emit_sweep's count
# load_and_monitor, not sweep_states: one state per ELF means there is no loop to run, and this
# is the scenario that reliably captures a full burst. The start state comes from the data
# folder, so sweeping folders is sweeping start states.
SCENARIO=tests/galena/perf/load_and_monitor.spm.c
COMPILE_ARGS="CORE_TESTED=1 SAMPLE_COUNT=256 SAMPLE_INTERVAL=0 PRINT_ROWS=0"
PLL_FREQ=512
RUN_TIMEOUT=0
RUN_NAME="sweep_11"

# --- where things go ---------------------------------------------------------
# RUN_NAME picks the subfolder under experiments/<problem>/, so several sweeps of the same
# problem can sit side by side. Either edit these, or override from the command line without
# touching the file:
#     RUN_NAME=roll8 sw/tools/run_sweep.sh
#     LOG_DIR=/tmp/try sw/tools/run_sweep.sh --run
RUN_NAME=${RUN_NAME:-sweep}

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SW=$ROOT/submodules/lagd-im/sw
OUT=${OUT:-$ROOT/experiments/$PROBLEM/$RUN_NAME}
ELF_DIR=${ELF_DIR:-$OUT/elf}
LOG_DIR=${LOG_DIR:-$OUT/runs}
TARGET=${SCENARIO%.c}.elf                       # tests/galena/perf/sweep_states.spm.elf
NAME=$(basename "${SCENARIO%.spm.c}")

do_build=1
do_run=1
case "${1:-}" in
    --build) do_run=0 ;;
    --run) do_build=0 ;;
    "") ;;
    *) echo "usage: $(basename "$0") [--build|--run]" >&2; exit 2 ;;
esac

mkdir -p "$ELF_DIR" "$LOG_DIR"

# Say where things are going. RUN_NAME is easy to change between a build and a run, and the only
# symptom of that is an output folder that stays empty while a full set sits somewhere else.
echo "problem  $PROBLEM   prefix $PREFIX   count $COUNT   run name $RUN_NAME"
echo "elfs     $ELF_DIR"
echo "logs     $LOG_DIR"

# Check every data folder up front. Without this the build loop gets partway through and stops,
# leaving a set of ELFs that looks complete but is not -- and a PREFIX that does not match
# emit_sweep's is the easy way to end up there.
have=$(find "$SW/tests/ref/data" -maxdepth 1 -type d -name "${PREFIX}_*" | wc -l)
missing=""
for k in $(seq -f "%03g" 0 $((COUNT - 1))); do
    [ -d "$SW/tests/ref/data/${PREFIX}_$k" ] || missing="$missing ${PREFIX}_$k"
done
if [ -n "$missing" ]; then
    echo "PREFIX=$PREFIX COUNT=$COUNT, but these data folders are missing:" >&2
    echo "  ${missing# }" | fold -s -w 100 >&2
    echo "found $have folder(s) matching ${PREFIX}_* -- check PREFIX against emit_sweep's" >&2
    echo "second argument, and COUNT against its third, then re-run gen_ising_problem.py" >&2
    exit 1
fi
echo "$PREFIX: $COUNT data folders present ($have matching on disk)"

# --- build: one ELF per data folder ------------------------------------------
# The build always lands on the same path inside the submodule, so each one is copied out to a
# per-state name before the next build overwrites it.
if [ "$do_build" = 1 ]; then
    for k in $(seq -f "%03g" 0 $((COUNT - 1))); do
        folder=${PREFIX}_$k
        if [ ! -d "$SW/tests/ref/data/$folder" ]; then
            echo "missing data folder $folder -- run emit_sweep() first" >&2
            exit 1
        fi
        echo "=== building $folder"
        # The generated data headers are file targets whose prerequisites sit in the data folder.
        # Switching DATA_FOLDER does not make them out of date -- the header is newer than every
        # folder, since emit_sweep() writes them all before the first build -- so make would keep
        # the previous state's spins. Delete them and they are regenerated from this folder.
        rm -f "$SW"/include/gen/model_j_data.h "$SW"/include/gen/model_j_data_sec.h \
              "$SW"/include/gen/model_f_data.h "$SW"/include/gen/model_f_data_sec.h \
              "$SW"/include/gen/spin_data.h "$SW"/include/gen/spin_data_sec.h \
              "$SW"/include/gen/state_out_ref.h "$SW"/include/gen/state_out_ref_sec.h
        make -C "$SW" DATA_FOLDER="$folder" COMPILE_ARGS="$COMPILE_ARGS" "$TARGET"
        cp "$SW/$TARGET" "$ELF_DIR/${NAME}_$k.elf"
    done
    echo "built $COUNT ELFs into $ELF_DIR"
fi

# --- run: one chip session per ELF -------------------------------------------
if [ "$do_run" = 1 ]; then
    cd "$ROOT"
    for k in $(seq -f "%03g" 0 $((COUNT - 1))); do
        elf=$ELF_DIR/${NAME}_$k.elf
        log=$LOG_DIR/$k.log
        if [ ! -f "$elf" ]; then
            echo "missing $elf -- build first" >&2
            exit 1
        fi
        echo "=== running $k -> $log"
        python -m sw.uart.send_uart --run-timeout "$RUN_TIMEOUT" --pll-freq "$PLL_FREQ" "$elf" \
            | tee "$log"
    done
    echo "logs in $LOG_DIR"
    echo "plot them by pointing LOG at that directory in sw/tools/plot_sweep.py"
fi
