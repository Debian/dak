#!/bin/bash
# -*- mode: sh -*-
#
# © 2017-2018 Ansgar Burchardt <ansgar@debian.org>
# License: GPL-2+
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

set -e
set -u
set -o pipefail

dak-setup() {
  # Get the parent directory of the current script
  if [[ ! -v DAK_ROOT ]]; then
    local DAK_ROOT="$(cd $(dirname "$0")/..; pwd)"
  fi
  local setupdir="${DAK_ROOT}/setup"

  # This script can be used both for the integration tests and for actual
  # creation of a system dak. This is governed by the DAK_INTEGRATION_TEST var.
  if [[ ! -v DAK_INTEGRATION_TEST ]]; then
    PG_CMD="sudo -E -u postgres"
    SYS_CMD="sudo -E"
    USER_CMD="sudo -E -u dak -s -H"
    PYTHON_COVERAGE=
  else
    PG_CMD=""
    SYS_CMD=""
    USER_CMD=""
    if [ "${RUN_COVERAGE:-n}" = "y" ]; then
      if [ "${DAK_PYTHON3:-n}" = "y" ]; then
        COVERAGE_CMD=python3-coverage
      else
        COVERAGE_CMD=python-coverage
      fi
      PYTHON_COVERAGE="${COVERAGE_CMD} run --rcfile ${DAK_ROOT}/.coveragerc --parallel-mode"
    else
      PYTHON_COVERAGE=
    fi
  fi

  # Get default values from init_vars.
  # This sets the DAKBASE variable in case it didn't have a value.
  . ${setupdir}/init_vars

  # Ensure that DAKBASE exists
  $SYS_CMD mkdir -p ${DAKBASE}

  # Ensure the right permissions when not running tests
  if [[ ! -v DAK_INTEGRATION_TEST ]]; then
    $SYS_CMD chown dak:ftpmaster ${DAKBASE}
    $SYS_CMD chmod 2775 ${DAKBASE}
  fi

  # When setting up the system DB, this needs to be run as postgres
  (cd ${setupdir}; $PG_CMD ./init_db)
  if [[ ${PGUSER:-} != dak && -v ${PGUSER} ]]; then
    $PG_CMD psql -c "GRANT dak TO \"${PGUSER}\""
  fi

  $USER_CMD mkdir -p ${DAKBASE}/etc ${DAKBASE}/bin ${DAKBASE}/keyrings ${DAKBASE}/tmp

  # Copy/Link the email templates into the /srv/dak tree.
  if [[ ! -v DAK_INTEGRATION_TEST ]]; then
    $USER_CMD cp -r ${DAK_ROOT}/templates ${DAKBASE}/
  else
    $USER_CMD ln -s ${DAK_ROOT}/templates ${DAKBASE}/
  fi

  # Import the schema.  We redirect STDOUT to /dev/null as otherwise it's
  # impossible to see if something fails.
  $USER_CMD psql -f ${setupdir}/current_schema.sql -d ${PGDATABASE} >/dev/null

  # Set up some core data in PGDATABASE to get started
  (cd ${setupdir}; $USER_CMD ./init_core)

  # Create a minimal dak.conf
  export DAK_CONFIG="${DAKBASE}/etc/dak.conf"
  (cd ${setupdir}; ./init_minimal_conf | $USER_CMD tee ${DAK_CONFIG} >/dev/null)
  $USER_CMD echo 'DB::Role "dak";' | tee -a ${DAK_CONFIG} >/dev/null

  if [[ ! -v DAK_INTEGRATION_TEST ]]; then
    ln -s ${DAK_ROOT}/dak/dak.py ${DAKBASE}/bin/dak
  else
    # wrapper to collect coverage information
    ln -s ${DAK_ROOT}/integration-tests/dak-coverage.sh ${DAKBASE}/bin/dak
  fi

  # Update the database schema
  $USER_CMD ${DAKBASE}/bin/dak update-db --yes
  # Run dak init-dirs to set up the initial /srv/dak tree
  $USER_CMD ${DAKBASE}/bin/dak init-dirs
}

dak-setup
