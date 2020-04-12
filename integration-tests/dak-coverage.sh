#!/bin/bash

# wrapper to collect coverage info when running dak

if [ "$DAK_PYTHON3" = "y" ]
then
	exec python3-coverage run --rcfile "${DAK_ROOT}/.coveragerc" --source "${DAK_ROOT}" --parallel-mode "${DAK_ROOT}/dak/dak.py" "$@"
fi

if [ "$RUN_COVERAGE" = "y" ]
then
	exec python-coverage run --rcfile "${DAK_ROOT}/.coveragerc" --parallel-mode "${DAK_ROOT}/dak/dak.py" "$@"
else
	exec "${DAK_ROOT}/dak/dak.py" "$@"
fi
