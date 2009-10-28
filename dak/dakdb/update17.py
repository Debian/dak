#!/usr/bin/env python
# coding=utf8

"""
Adding a trainee field to the process-new notes

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

################################################################################


################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError

################################################################################

def suites():
    """
    return a list of suites to operate on
    """
    if Config().has_key( "%s::%s" %(options_prefix,"Suite")):
        suites = utils.split_args(Config()[ "%s::%s" %(options_prefix,"Suite")])
    else:
        suites = [ 'unstable', 'testing' ]
#            suites = Config().SubTree("Suite").List()

    return suites

def arches(cursor, suite):
    """
    return a list of archs to operate on
    """
    arch_list = []
    cursor.execute("EXECUTE arches_q(%d)" % (suite))
    while True:
        r = cursor.fetchone()
        if not r:
            break

        if r[1] != "source" and r[1] != "all":
            arch_list.append((r[0], r[1]))

    return arch_list

def do_update(self):
    """
    Adding contents table as first step to maybe, finally getting rid
    of apt-ftparchive
    """

    print __doc__

    try:
        c = self.db.cursor()
        c.execute("""CREATE TABLE deb_contents (
        file text,
        section text,
        package text,
        binary_id integer,
        arch integer,
        suite integer,
        component integer)""" )
        
        c.execute("""CREATE TABLE udeb_contents (
        file text,
        section text,
        package text,
        binary_id integer,
        suite integer,
        component integer )""" )
        
        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_arch_fkey
        FOREIGN KEY (arch) REFERENCES architecture(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_arch_fkey
        FOREIGN KEY (arch) REFERENCES architecture(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_suite_fkey
        FOREIGN KEY (suite) REFERENCES suite(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_suite_fkey
        FOREIGN KEY (suite) REFERENCES suite(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_binary_fkey
        FOREIGN KEY (binary_id) REFERENCES binaries(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_binary_fkey
        FOREIGN KEY (binary_id) REFERENCES binaries(id)
        ON DELETE CASCADE;""")

        c.execute("""CREATE INDEX ind_deb_contents_binary ON deb_contents(binary_id);""" )

        arches_q = """PREPARE arches_q(int) as
        SELECT s.architecture, a.arch_string
        FROM suite_architectures s
        JOIN architecture a ON (s.architecture=a.id)
        WHERE suite = $1"""
        
        suites = self.suites()

        for suite in [i.lower() for i in suites]:
            suite_id = DBConn().get_suite_id(suite)
            arch_list = arches(c, suite_id)
            arch_list = arches(c, suite_id)

            for (arch_id,arch_str) in arch_list:
                c.execute( "CREATE INDEX ind_deb_contents_%s_%s ON deb_contents (arch,suite) WHERE (arch=2 OR arch=%d) AND suite=$d"%(arch_str,suite,arch_id,suite_id) )

            for section, sname in [("debian-installer","main"),
                                  ("non-free/debian-installer", "nonfree")]:
                c.execute( "CREATE INDEX ind_udeb_contents_%s_%s ON udeb_contents (section,suite) WHERE section=%s AND suite=$d"%(sname,suite,section,suite_id) )
                

   Column   |  Type   | Modifiers
   ------------+---------+-----------
    package    | text    | not null
     suite      | integer | not null
      component  | integer | not null
       priority   | integer |
        section    | integer | not null
         type       | integer | not null
          maintainer | text    |
          
        c.execute("""CREATE TABLE deb_contents (
        file text,
        section text,
        package text,
        binary_id integer,
        arch integer,
        suite integer,
        component integer)""" )
        

CREATE FUNCTION update_contents_for_override() RETURNS trigger AS $update_contents_for_override$
BEGIN
    UPDATE deb_contents  SET section=NEW.section, component=NEW.component
    WHERE deb_contents.package=OLD.package
                            

DELETE FROM 
NEW.last_date := current_timestamp;
NEW.last_user := current_user;
RETURN NEW;
END;
$update_contents_for_override$ LANGUAGE plpgsql;


        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError, "Unable to apply process-new update 14, rollback issued. Error message : %s" % (str(msg))
"""
         INSERT INTO deb_contents SELECT (p.path||'/'||n.file) AS file,
                  s.section AS section,
                  b.package AS package,
                  b.id AS binary_id,
                  b.architecture AS arch,
                  o.suite AS suited,
                  o.component AS componentd,
                  o.type AS otype_id
          FROM content_associations c 
          JOIN content_file_paths p ON (c.filepath=p.id)
          JOIN content_file_names n ON (c.filename=n.id)
          JOIN binaries b ON (b.id=c.binary_pkg)
          JOIN architecture a ON (b.architecture = a.id)
          JOIN override o ON (o.package=b.package)
          JOIN bin_associations ba on ba.suite=o.suite and ba.bin=b.id
          JOIN section s ON (s.id=o.section)
          where b.type='deb';

         INSERT INTO udeb_contents SELECT (p.path||'/'||n.file) AS file,
                  s.section AS section,
                  b.package AS package,
                  b.id AS binary_id,
                  b.architecture AS arch,
                  o.suite AS suited,
                  o.component AS componentd,
                  o.type AS otype_id
          FROM content_associations c 
          JOIN content_file_paths p ON (c.filepath=p.id)
          JOIN content_file_names n ON (c.filename=n.id)
          JOIN binaries b ON (b.id=c.binary_pkg)
          JOIN architecture a ON (b.architecture = a.id)
          JOIN override o ON (o.package=b.package)
          JOIN section s ON (s.id=o.section)
          where b.type='udeb'
"""

"""
CREATE INDEX ind_archid ON contents(arch);
CREATE INDEX ind_archid_amd64 ON contents(arch) WHERE arch=16;
CREATE INDEX ind_suite ON contents(suite);
CREATE INDEX ind_suite_unstable ON contents(suite) WHERE suite=5;
CREATE INDEX ind_overridetype ON contents(otype);
CREATE INDEX ind_overridetype_deb ON contents(otype) WHERE otype=7;
CREATE INDEX ind_packagetype ON contents(packagetype);
CREATE INDEX ind_packagetype_deb ON contents(packagetype) WHERE packagetype='deb';
CREATE INDEX ind_package ON contents(package);

 CREATE INDEX ind_suite_otype ON contents(suite, otype) WHERE suite=5 AND otype=7;
 CREATE INDEX ind_suite_otype_arch ON contents(suite, otype, arch) WHERE suite=5 AND otype=7 AND arch=16;
 CREATE INDEX ind_suite_otype_package ON contents(suite, otype, packagetype) WHERE suite=5 AND otype=7 AND packagetype='deb';
 CREATE INDEX ind_suite_otype_package_notdeb ON contents(suite, otype, packagetype) WHERE suite=5 AND otype=7 AND packagetype!='deb';
                                                                                                                                                                                          """

CREATE INDEX ind_deb_contents_binary ON deb_contents(binary_id);

CREATE INDEX ind_deb_contents_arch_alpha_unstable ON deb_contents(arch) where (arch=2 or arch=3) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hurd_i386_unstable ON deb_contents(arch) where (arch=2 or arch=4) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hppa_unstable ON deb_contents(arch) where (arch=2 or arch=5) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_arm_unstable ON deb_contents(arch) where (arch=2 or arch=6) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_i386_unstable ON deb_contents(arch) where (arch=2 or arch=7) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_m68k_unstable ON deb_contents(arch) where (arch=2 or arch=8) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mips_unstable ON deb_contents(arch) where (arch=2 or arch=9) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mipsel_unstable ON deb_contents(arch) where (arch=2 or arch=10) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_powerpc_unstable ON deb_contents(arch) where (arch=2 or arch=11) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sh_unstable ON deb_contents(arch) where (arch=2 or arch=12) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sparc_unstable ON deb_contents(arch) where (arch=2 or arch=13) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_s390_unstable ON deb_contents(arch) where (arch=2 or arch=14) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_ia64_unstable ON deb_contents(arch) where (arch=2 or arch=15) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_amd64_unstable ON deb_contents(arch) where (arch=2 or arch=16) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_armel_unstable ON deb_contents(arch) where (arch=2 or arch=17) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_i386_unstable ON deb_contents(arch) where (arch=2 or arch=25) AND suite=5 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_amd64_unstable ON deb_contents(arch) where (arch=2 or arch=26) AND suite=5 AND otype=7;

CREATE INDEX ind_deb_contents_arch_alpha_stable ON deb_contents(arch) where (arch=2 or arch=3) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hurd_i386_stable ON deb_contents(arch) where (arch=2 or arch=4) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hppa_stable ON deb_contents(arch) where (arch=2 or arch=5) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_arm_stable ON deb_contents(arch) where (arch=2 or arch=6) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_i386_stable ON deb_contents(arch) where (arch=2 or arch=7) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_m68k_stable ON deb_contents(arch) where (arch=2 or arch=8) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mips_stable ON deb_contents(arch) where (arch=2 or arch=9) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mipsel_stable ON deb_contents(arch) where (arch=2 or arch=10) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_powerpc_stable ON deb_contents(arch) where (arch=2 or arch=11) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sh_stable ON deb_contents(arch) where (arch=2 or arch=12) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sparc_stable ON deb_contents(arch) where (arch=2 or arch=13) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_s390_stable ON deb_contents(arch) where (arch=2 or arch=14) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_ia64_stable ON deb_contents(arch) where (arch=2 or arch=15) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_amd64_stable ON deb_contents(arch) where (arch=2 or arch=16) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_armel_stable ON deb_contents(arch) where (arch=2 or arch=17) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_i386_stable ON deb_contents(arch) where (arch=2 or arch=25) AND suite=2 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_amd64_stable ON deb_contents(arch) where (arch=2 or arch=26) AND suite=2 AND otype=7;

CREATE INDEX ind_deb_contents_arch_alpha_testing ON deb_contents(arch) where (arch=2 or arch=3) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hurd_i386_testing ON deb_contents(arch) where (arch=2 or arch=4) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hppa_testing ON deb_contents(arch) where (arch=2 or arch=5) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_arm_testing ON deb_contents(arch) where (arch=2 or arch=6) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_i386_testing ON deb_contents(arch) where (arch=2 or arch=7) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_m68k_testing ON deb_contents(arch) where (arch=2 or arch=8) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mips_testing ON deb_contents(arch) where (arch=2 or arch=9) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mipsel_testing ON deb_contents(arch) where (arch=2 or arch=10) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_powerpc_testing ON deb_contents(arch) where (arch=2 or arch=11) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sh_testing ON deb_contents(arch) where (arch=2 or arch=12) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sparc_testing ON deb_contents(arch) where (arch=2 or arch=13) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_s390_testing ON deb_contents(arch) where (arch=2 or arch=14) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_ia64_testing ON deb_contents(arch) where (arch=2 or arch=15) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_amd64_testing ON deb_contents(arch) where (arch=2 or arch=16) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_armel_testing ON deb_contents(arch) where (arch=2 or arch=17) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_i386_testing ON deb_contents(arch) where (arch=2 or arch=25) AND suite=4 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_amd64_testing ON deb_contents(arch) where (arch=2 or arch=26) AND suite=4 AND otype=7;

CREATE INDEX ind_deb_contents_arch_alpha_oldstable ON deb_contents(arch) where (arch=2 or arch=3) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hurd_i386_oldstable ON deb_contents(arch) where (arch=2 or arch=4) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_hppa_oldstable ON deb_contents(arch) where (arch=2 or arch=5) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_arm_oldstable ON deb_contents(arch) where (arch=2 or arch=6) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_i386_oldstable ON deb_contents(arch) where (arch=2 or arch=7) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_m68k_oldstable ON deb_contents(arch) where (arch=2 or arch=8) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mips_oldstable ON deb_contents(arch) where (arch=2 or arch=9) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_mipsel_oldstable ON deb_contents(arch) where (arch=2 or arch=10) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_powerpc_oldstable ON deb_contents(arch) where (arch=2 or arch=11) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sh_oldstable ON deb_contents(arch) where (arch=2 or arch=12) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_sparc_oldstable ON deb_contents(arch) where (arch=2 or arch=13) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_s390_oldstable ON deb_contents(arch) where (arch=2 or arch=14) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_ia64_oldstable ON deb_contents(arch) where (arch=2 or arch=15) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_amd64_oldstable ON deb_contents(arch) where (arch=2 or arch=16) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_armel_oldstable ON deb_contents(arch) where (arch=2 or arch=17) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_i386_oldstable ON deb_contents(arch) where (arch=2 or arch=25) AND suite=14 AND otype=7;
CREATE INDEX ind_deb_contents_arch_kfreebsd_amd64_oldstable ON deb_contents(arch) where (arch=2 or arch=26) AND suite=14 AND otype=7;
