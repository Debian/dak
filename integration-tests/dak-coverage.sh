#!/bin/bash

# wrapper to collect coverage info when running dak

if [ "$RUN_COVERAGE" = "y" ]
then
	exec python-coverage run --rcfile "${DAK_ROOT}/.coveragerc" --parallel-mode "${DAK_ROOT}/dak/dak.py" "$@"
else
	exec "${DAK_ROOT}/dak/dak.py" "$@"
fi
