"""external signature requests

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2018  Ansgar Burchardt <ansgar@debian.org>
@license: GNU General Public License version 2 or later
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import json
import sqlalchemy.sql as sql
import sqlalchemy.dialects.postgresql as pgsql

import daklib.gpg

from daklib.config import Config
from daklib.dbconn import DBConn


def export_external_signature_requests(session, path):
    tbl_arch = DBConn().tbl_architecture
    tbl_ba = DBConn().tbl_bin_associations
    tbl_bin = DBConn().tbl_binaries
    tbl_src = DBConn().tbl_source
    tbl_esr = DBConn().tbl_external_signature_requests
    tbl_suite = DBConn().tbl_suite

    query = sql.select([tbl_bin.c.package, tbl_src.c.source, tbl_suite.c.suite_name, tbl_suite.c.codename, tbl_arch.c.arch_string, sql.func.max(tbl_bin.c.version)]) \
            .select_from(tbl_esr.join(tbl_suite).join(tbl_ba, tbl_ba.c.id == tbl_esr.c.association_id).join(tbl_bin).join(tbl_arch).join(tbl_src, tbl_bin.c.source == tbl_src.c.id)) \
            .group_by(tbl_bin.c.package, tbl_src.c.source, tbl_suite.c.suite_name, tbl_suite.c.codename, tbl_arch.c.arch_string)
    requests = session.execute(query)

    data = {
        'packages': [
            {
                'package':      row[0],
                'source':       row[1],
                'suite':        row[2],
                'codename':     row[3],
                'architecture': row[4],
                'version':      row[5],
            }
            for row in requests],
    }

    with open(path, 'w') as fh:
        json.dump(data, fh, indent=2)


def sign_external_signature_requests(session, path, keyids, args={}):
    outpath = '{}.gpg'.format(path)
    with open(path, 'r') as infile, open(outpath, 'w') as outfile:
        daklib.gpg.sign(infile, outfile, keyids, inline=False, **args)


def add_external_signature_request(session, target_suite, suite, binary):
    tbl_ba = DBConn().tbl_bin_associations
    tbl_esr = DBConn().tbl_external_signature_requests

    select = sql.select([tbl_ba.c.id, target_suite.suite_id]).where((tbl_ba.c.suite == suite.suite_id) & (tbl_ba.c.bin == binary.binary_id))
    insert = pgsql.insert(tbl_esr).from_select([tbl_esr.c.association_id, tbl_esr.c.suite_id], select).on_conflict_do_nothing()
    session.execute(insert)


def check_upload_for_external_signature_request(session, target_suite, suite, binary):
    if 'External-Signature-Requests' not in Config():
        return
    config = Config().subtree('External-Signature-Requests')
    config_sources = config.subtree('Sources')

    source = binary.source

    if source.source not in config_sources:
        return
    src_config = config_sources.subtree(source.source)

    if binary.package not in src_config.value_list('Packages'):
        return

    suites = config.value_list('Default-Suites')
    if 'Suites' in src_config:
        suites = src_config.value_list('Suites')
    if target_suite.suite_name not in suites:
        return

    archs = config.value_list('Default-Architectures')
    if 'Architectures' in src_config:
        archs = src_config.value_list('Architectures')
    if binary.architecture.arch_string not in archs:
        return

    add_external_signature_request(session, target_suite, suite, binary)
