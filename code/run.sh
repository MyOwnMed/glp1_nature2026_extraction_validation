#!/bin/bash
#
# Runs every experiment and fails loudly if any of them fails.
#
#   set -e           stop on the first failing command
#   set -u           treat unset variables as errors
#   set -o pipefail  a failing command in a pipeline fails the pipeline
#
set -euo pipefail

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Define directories
RESULTS_DIR="../results"
DATA_DIR="../data"

# Create results directory if it doesn't exist
mkdir -p "$RESULTS_DIR"

FAILED_COUNT=0
FAILED_LIST=""

# Run one experiment. stdout and stderr both go to the results file so the log
# is complete; on failure the tail is echoed to stderr so a traceback is not
# silently buried, and the exit status is recorded rather than discarded.
run_step () {
    label="$1"; shift
    outfile="$1"; shift
    echo "Running ${label}..."
    status=0
    "$@" > "${outfile}" 2>&1 || status=$?
    if [ "${status}" -eq 0 ]; then
        echo "  OK -> ${outfile}"
    else
        echo "  FAILED (exit ${status}): ${label}" >&2
        echo "  --- last 20 lines of ${outfile} ---" >&2
        tail -20 "${outfile}" >&2 || true
        echo "  ---" >&2
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_LIST="${FAILED_LIST}${FAILED_LIST:+, }${label}"
    fi
}

run_step "Unit tests" "$RESULTS_DIR/tests_results.txt" \
    python3 -m unittest discover -s . -p 'test_*.py' -v

run_step "Experiment 2" "$RESULTS_DIR/experiment2_results.txt" \
    python3 experiment2.py

run_step "Experiment 3 (Medications)" "$RESULTS_DIR/experiment3_med_results.txt" \
    python3 experiment3_med.py

run_step "Experiment 3" "$RESULTS_DIR/experiment3_results.txt" \
    python3 experiment3.py

run_step "Experiment 4" "$RESULTS_DIR/experiment4_results.txt" \
    python3 experiment4.py \
        --json "$DATA_DIR/hpo_timeline_prevalence.json" \
        --data_dir "$DATA_DIR" \
        --output_dir "$RESULTS_DIR"

# Unnormalized sensitivity analysis for Experiment 4. Normalization divides
# prevalence by per-window event counts, so part of the before/after delta
# would otherwise be driven by encounter volume rather than prevalence change.
run_step "Experiment 4 (unnormalized sensitivity)" "$RESULTS_DIR/experiment4_unnormalized_results.txt" \
    python3 experiment4.py \
        --json "$DATA_DIR/hpo_timeline_prevalence.json" \
        --data_dir "$DATA_DIR" \
        --output_dir "$RESULTS_DIR" \
        --suffix experiment4_unnormalized \
        --no-normalize

if [ "${FAILED_COUNT}" -gt 0 ]; then
    echo "" >&2
    echo "${FAILED_COUNT} step(s) FAILED: ${FAILED_LIST}" >&2
    echo "Check $RESULTS_DIR for partial outputs." >&2
    exit 1
fi

echo ""
echo "All experiments completed successfully. Check $RESULTS_DIR for outputs."
