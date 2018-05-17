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


dak-setup() {
  # Get the parent directory of the current script
  local DAK_ROOT="$(cd $(dirname "$0")/..; pwd)"
  local setupdir="${DAK_ROOT}/setup"

  # This script can be used both for the integration tests and for actual
  # creation of a system dak. This is governed by the DAK_INTEGRATION_TEST var.
  if [[ ! -v DAK_INTEGRATION_TEST ]]; then
    PG_CMD="sudo -u postgres"
    SYS_CMD="sudo"
    USER_CMD="sudo -u dak -s -H"
  else
    PG_CMD=""
    SYS_CMD=""
    USER_CMD=""
  fi

  # Get default values from init_vars.
  # This sets the DAKBASE variable in case it didn't have a value.
  . ${setupdir}/init_vars

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
  $USER_CMD psql -f ${setupdir}/current_schema.sql -d projectb >/dev/null
  unset PGDATABASE

  # Set up some core data in projectb to get started
  (cd ${setupdir}; $USER_CMD ./init_core)

  # Create a minimal dak.conf
  export DAK_CONFIG="${DAKBASE}/etc/dak.conf"
  (cd ${setupdir}; ./init_minimal_conf | $USER_CMD tee ${DAK_CONFIG} >/dev/null)
  $USER_CMD echo 'DB::Role "dak";' | tee -a ${DAK_CONFIG} >/dev/null

  ln -s ${DAK_ROOT}/dak/dak.py ${DAKBASE}/bin/dak

  # Update the database schema
  $USER_CMD ${DAK_ROOT}/dak/dak.py update-db --yes
  # Run dak init-dirs to set up the initial /srv/dak tree
  $USER_CMD ${DAK_ROOT}/dak/dak.py init-dirs
}

dak-setup
