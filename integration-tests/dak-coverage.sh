#!/bin/bash

# wrapper to collect coverage info when running dak

export COVERAGE_FILE="${DAK_ROOT}/.coverage"

if [ "$RUN_COVERAGE" = "y" ]
then
	exec python3-coverage run --rcfile "${DAK_ROOT}/.coveragerc" --source "${DAK_ROOT}" --parallel-mode "${DAK_ROOT}/dak/dak.py" "$@"
else
	exec python3 "${DAK_ROOT}/dak/dak.py" "$@"
fi
