#!/usr/bin/env python

"""
Add views for new obsolete source detection.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Torsten Werner <twerner@debian.org>
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

import psycopg2

def do_update(self):
    print "Add/modify views for obsolete source detection."

    try:
        c = self.db.cursor()

        print "Replace old views."
        # joins src_associations and source
        c.execute("""
CREATE OR REPLACE VIEW source_suite AS
    SELECT src_associations.id, source.id AS src, source.source, source.version,
           src_associations.suite, suite.suite_name, source.install_date
        FROM source
        JOIN src_associations ON source.id = src_associations.source
        JOIN suite ON suite.id = src_associations.suite;
            """)
        # joins bin_associations and binaries
        c.execute("""
CREATE OR REPLACE VIEW bin_associations_binaries AS
    SELECT bin_associations.id, bin_associations.bin, binaries.package,
           binaries.version, bin_associations.suite, binaries.architecture,
           binaries.source
        FROM bin_associations
        JOIN binaries ON bin_associations.bin = binaries.id;
            """)

        print "Drop old views."
        c.execute("DROP VIEW IF EXISTS source_suite_unique CASCADE")
        c.execute("DROP VIEW IF EXISTS obsolete_source CASCADE")
        c.execute("DROP VIEW IF EXISTS source_bin CASCADE")
        c.execute("DROP VIEW IF EXISTS newest_source_bab CASCADE")

        print "Create new views."
        # returns source package names from suite without duplicates;
        # rationale: cruft-report and rm cannot handle duplicates (yet)
        c.execute("""
CREATE VIEW source_suite_unique
    AS SELECT source, suite
        FROM source_suite GROUP BY source, suite HAVING count(*) = 1;
            """)
        # returns obsolete sources without binaries in the same suite;
        # outputs install_date to detect source only (or binary throw away)
        # uploads; duplicates are skipped
        c.execute("""
CREATE VIEW obsolete_source
    AS SELECT ss.src, ss.source, ss.version, ss.suite,
        to_char(ss.install_date, 'YYYY-MM-DD') AS install_date
        FROM source_suite ss
        JOIN source_suite_unique ssu
            ON ss.source = ssu.source AND ss.suite = ssu.suite
        LEFT JOIN bin_associations_binaries bab
            ON ss.src = bab.source AND ss.suite = bab.suite
            WHERE bab.id IS NULL;
            """)
        # returns source package names and its binaries from any suite
        c.execute("""
CREATE VIEW source_bin
    AS SELECT b.package, MAX(b.version) AS version, sas.source
        FROM binaries b
        JOIN src_associations_src sas
            ON b.source = sas.src
        GROUP BY b.package, sas.source
            """)
        # returns binaries from suite and their source with max(version)
        # grouped by source name, binary name, and suite
        c.execute("""
CREATE VIEW newest_source_bab
    AS SELECT sas.source, MAX(sas.version) AS srcver, bab.package, bab.suite
        FROM src_associations_src sas
        JOIN bin_associations_binaries bab ON sas.src = bab.source
            GROUP BY sas.source, bab.package, bab.suite;
            """)

        print "Grant permissions to views."
        c.execute("GRANT SELECT ON binfiles_suite_component_arch TO PUBLIC;");
        c.execute("GRANT SELECT ON srcfiles_suite_component TO PUBLIC;");
        c.execute("GRANT SELECT ON binaries_suite_arch TO PUBLIC;");
        c.execute("GRANT SELECT ON newest_all_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON obsolete_any_by_all_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON newest_any_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON obsolete_any_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON source_suite TO PUBLIC;");
        c.execute("GRANT SELECT ON newest_source TO PUBLIC;");
        c.execute("GRANT SELECT ON newest_src_association TO PUBLIC;");
        c.execute("GRANT SELECT ON any_associations_source TO PUBLIC;");
        c.execute("GRANT SELECT ON src_associations_src TO PUBLIC;");
        c.execute("GRANT SELECT ON almost_obsolete_src_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON obsolete_src_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON bin_associations_binaries TO PUBLIC;");
        c.execute("GRANT SELECT ON src_associations_bin TO PUBLIC;");
        c.execute("GRANT SELECT ON almost_obsolete_all_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON obsolete_all_associations TO PUBLIC;");
        c.execute("GRANT SELECT ON source_suite_unique TO PUBLIC;");
        c.execute("GRANT SELECT ON obsolete_source TO PUBLIC;");
        c.execute("GRANT SELECT ON source_bin TO PUBLIC;");
        c.execute("GRANT SELECT ON newest_source_bab TO PUBLIC;");

        print "Committing"
        c.execute("UPDATE config SET value = '27' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError, msg:
        self.db.rollback()
        raise DBUpdateError, "Database error, rollback issued. Error message : %s" % (str(msg))

