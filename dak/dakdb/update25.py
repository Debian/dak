#!/usr/bin/env python

"""
Add views for new dominate command.

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
    print "Add views for generate_filelist to database."

    try:
        c = self.db.cursor()

        print "Drop old views."
        c.execute("DROP VIEW IF EXISTS binaries_suite_arch CASCADE")
        c.execute("DROP VIEW IF EXISTS newest_all_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS obsolete_any_by_all_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS newest_any_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS obsolete_any_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS source_suite CASCADE")
        c.execute("DROP VIEW IF EXISTS newest_source CASCADE")
        c.execute("DROP VIEW IF EXISTS newest_src_association CASCADE")
        c.execute("DROP VIEW IF EXISTS any_associations_source CASCADE")
        c.execute("DROP VIEW IF EXISTS src_associations_src CASCADE")
        c.execute("DROP VIEW IF EXISTS almost_obsolete_src_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS obsolete_src_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS bin_associations_binaries CASCADE")
        c.execute("DROP VIEW IF EXISTS src_associations_bin CASCADE")
        c.execute("DROP VIEW IF EXISTS almost_obsolete_all_associations CASCADE")
        c.execute("DROP VIEW IF EXISTS obsolete_all_associations CASCADE")

        print "Create new views."
        c.execute("""
CREATE VIEW binaries_suite_arch AS
    SELECT bin_associations.id, binaries.id AS bin, binaries.package,
           binaries.version, binaries.source, bin_associations.suite,
           suite.suite_name, binaries.architecture, architecture.arch_string
        FROM binaries JOIN bin_associations ON binaries.id = bin_associations.bin
        JOIN suite ON suite.id = bin_associations.suite
        JOIN architecture ON binaries.architecture = architecture.id;
	    """)
        c.execute("""
CREATE VIEW newest_all_associations AS
    SELECT package, max(version) AS version, suite, architecture
        FROM binaries_suite_arch
        WHERE architecture = 2 GROUP BY package, suite, architecture;
	    """)
        c.execute("""
CREATE VIEW obsolete_any_by_all_associations AS
    SELECT binaries_suite_arch.id, binaries_suite_arch.package,
           binaries_suite_arch.version, binaries_suite_arch.suite,
           binaries_suite_arch.architecture
        FROM binaries_suite_arch
        JOIN newest_all_associations
            ON (binaries_suite_arch.package = newest_all_associations.package AND
                binaries_suite_arch.version < newest_all_associations.version AND
                binaries_suite_arch.suite = newest_all_associations.suite AND
                binaries_suite_arch.architecture > 2);
	    """)
        c.execute("""
CREATE VIEW newest_any_associations AS
    SELECT package, max(version) AS version, suite, architecture
        FROM binaries_suite_arch
        WHERE architecture > 2 GROUP BY package, suite, architecture;
	    """)
        c.execute("""
CREATE VIEW obsolete_any_associations AS
    SELECT id, binaries_suite_arch.architecture, binaries_suite_arch.version,
           binaries_suite_arch.package, binaries_suite_arch.suite
        FROM binaries_suite_arch
        JOIN newest_any_associations
            ON binaries_suite_arch.architecture = newest_any_associations.architecture AND
               binaries_suite_arch.package = newest_any_associations.package AND
               binaries_suite_arch.suite = newest_any_associations.suite AND
               binaries_suite_arch.version != newest_any_associations.version;
	    """)
        c.execute("""
CREATE VIEW source_suite AS
    SELECT src_associations.id, source.id AS src , source.source, source.version,
           src_associations.suite, suite.suite_name
        FROM source
        JOIN src_associations ON source.id = src_associations.source
        JOIN suite ON suite.id = src_associations.suite;
	    """)
        c.execute("""
CREATE VIEW newest_source AS
    SELECT source, max(version) AS version, suite
        FROM source_suite
        GROUP BY source, suite;
	    """)
        c.execute("""
CREATE VIEW newest_src_association AS
    SELECT id, src, source, version, suite
        FROM source_suite
        JOIN newest_source USING (source, version, suite);
	    """)
        c.execute("""
CREATE VIEW any_associations_source AS
    SELECT bin_associations.id, bin_associations.suite, binaries.id AS bin,
           binaries.package, binaries.version AS binver, binaries.architecture,
           source.id AS src, source.source, source.version AS srcver
        FROM bin_associations
        JOIN binaries ON bin_associations.bin = binaries.id AND architecture != 2
        JOIN source ON binaries.source = source.id;
	    """)
        c.execute("""
CREATE VIEW src_associations_src AS
    SELECT src_associations.id, src_associations.suite, source.id AS src,
           source.source, source.version
        FROM src_associations
        JOIN source ON src_associations.source = source.id;
	    """)
        c.execute("""
CREATE VIEW almost_obsolete_src_associations AS
    SELECT src_associations_src.id, src_associations_src.src,
           src_associations_src.source, src_associations_src.version, suite
        FROM src_associations_src
        LEFT JOIN any_associations_source USING (src, suite)
        WHERE bin IS NULL;
	    """)
        c.execute("""
CREATE VIEW obsolete_src_associations AS
    SELECT almost.id, almost.src, almost.source, almost.version, almost.suite
        FROM almost_obsolete_src_associations as almost
    JOIN newest_src_association AS newest
        ON almost.source  = newest.source AND
           almost.version < newest.version AND
           almost.suite   = newest.suite;
	    """)
        c.execute("""
CREATE VIEW bin_associations_binaries AS
    SELECT bin_associations.id, bin_associations.bin, binaries.package,
           binaries.version, bin_associations.suite, binaries.architecture
        FROM bin_associations
        JOIN binaries ON bin_associations.bin = binaries.id;
	    """)
        c.execute("""
CREATE VIEW src_associations_bin AS
    SELECT src_associations.id, src_associations.source, src_associations.suite,
           binaries.id AS bin, binaries.architecture
        FROM src_associations
        JOIN source ON src_associations.source = source.id
        JOIN binaries ON source.id = binaries.source;
	    """)
        c.execute("""
CREATE VIEW almost_obsolete_all_associations AS
    SELECT bin_associations_binaries.id AS id, bin, bin_associations_binaries.package,
           bin_associations_binaries.version, suite
        FROM bin_associations_binaries
        LEFT JOIN src_associations_bin USING (bin, suite, architecture)
        WHERE source IS NULL AND architecture = 2;
	    """)
        c.execute("""
CREATE VIEW obsolete_all_associations AS
    SELECT almost.id, almost.bin, almost.package, almost.version, almost.suite
        FROM almost_obsolete_all_associations AS almost
        JOIN newest_all_associations AS newest
            ON almost.package = newest.package AND
               almost.version < newest.version AND
               almost.suite   = newest.suite;
	    """)

        print "Committing"
        c.execute("UPDATE config SET value = '25' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Database error, rollback issued. Error message : %s" % (str(msg)))

