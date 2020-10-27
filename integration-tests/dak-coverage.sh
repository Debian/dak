#!/bin/bash

# wrapper to collect coverage info when running dak

export COVERAGE_FILE="${DAK_ROOT}/.coverage"

PYTHON=python
if [ "$DAK_PYTHON3" = "y" ]
then
	PYTHON=python3
fi

if [ "$RUN_COVERAGE" = "y" ]
then
	exec "${PYTHON}"-coverage run --rcfile "${DAK_ROOT}/.coveragerc" --source "${DAK_ROOT}" --parallel-mode "${DAK_ROOT}/dak/dak.py" "$@"
else
	exec "${PYTHON}" "${DAK_ROOT}/dak/dak.py" "$@"
fi
