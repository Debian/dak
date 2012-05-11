#!/usr/bin/env python

"""
Output override files for apt-ftparchive and indices/
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2004, 2006  James Troup <james@nocrew.org>
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

# This is seperate because it's horribly Debian specific and I don't
# want that kind of horribleness in the otherwise generic 'dak
# make-overrides'.  It does duplicate code tho.

################################################################################

import os
import sys
import apt_pkg

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils

################################################################################

def usage(exit_code=0):
    print """Usage: dak make-overrides
Outputs the override tables to text files.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def do_list(output_file, suite, component, otype, session):
    """
    Fetch override data for suite from the database and dump it.

    @type output_file: fileobject
    @param output_file: where to write the overrides to

    @type suite: Suite object
    @param suite: A suite object describing the Suite

    @type component: Component object
    @param component: The name of the component

    @type otype: OverrideType object
    @param otype: object of type of override. deb/udeb/dsc

    @type session: SQLA Session
    @param session: the database session in use

    """
    # Here's a nice example of why the object API isn't always the
    # right answer.  On my laptop, the object version of the code
    # takes 1:45, the 'dumb' tuple-based one takes 0:16 - mhy

    if otype.overridetype == "dsc":
        #q = session.query(Override).filter_by(suite_id = suite.suite_id)
        #q = q.filter_by(component_id = component.component_id)
        #q = q.filter_by(overridetype_id = otype.overridetype_id)
        #q = q.join(Section).order_by(Section.section, Override.package)
        #for o in q.all():
        #    dat = (o.package, o.section.section, o.maintainer)
        #    output_file.write(utils.result_join(dat) + '\n')
        q = session.execute("SELECT o.package, s.section, o.maintainer FROM override o, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.section = s.id ORDER BY s.section, o.package" % (suite.suite_id, component.component_id, otype.overridetype_id))
        for i in q.fetchall():
            output_file.write(utils.result_join(i) + '\n')

    else:
        #q = session.query(Override).filter_by(suite_id = suite.suite_id)
        #q = q.filter_by(component_id = component.component_id)
        #q = q.filter_by(overridetype_id = otype.overridetype_id)
        #q = q.join(Priority).join(Section).order_by(Section.section, Priority.level, Override.package)
        #for o in q.all():
        #    dat = (o.package, o.priority.priority, o.section.section, o.maintainer)
        #    output_file.write(utils.result_join(dat) + '\n')
        q = session.execute("SELECT o.package, p.priority, s.section, o.maintainer FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.priority = p.id AND o.section = s.id ORDER BY s.section, p.level, o.package" % (suite.suite_id, component.component_id, otype.overridetype_id))
        for i in q.fetchall():
            output_file.write(utils.result_join(i) + '\n')

################################################################################

def main ():
    cnf = Config()
    Arguments = [('h',"help","Make-Overrides::Options::Help")]
    for i in [ "help" ]:
        if not cnf.has_key("Make-Overrides::Options::%s" % (i)):
            cnf["Make-Overrides::Options::%s" % (i)] = ""
    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Make-Overrides::Options")
    if Options["Help"]:
        usage()

    d = DBConn()
    session = d.session()

    for suite in session.query(Suite).filter(Suite.overrideprocess==True):
        if suite.untouchable:
            print "Skipping %s as it is marked as untouchable" % suite.suite_name
            continue

        sys.stderr.write("Processing %s...\n" % (suite.suite_name))
        override_suite = suite.overridecodename

        for component in session.query(Component).all():
            for otype in session.query(OverrideType).all():
                otype_name = otype.overridetype
                cname = component.component_name

                # TODO: Stick suffix info in database (or get rid of it)
                if otype_name == "deb":
                    suffix = ""
                elif otype_name == "udeb":
                    if cname == "contrib":
                        continue # Ick2
                    suffix = ".debian-installer"
                elif otype_name == "dsc":
                    suffix = ".src"
                else:
                    utils.fubar("Don't understand OverrideType %s" % otype.overridetype)

                cname = cname.replace('/', '_')
                filename = os.path.join(cnf["Dir::Override"], "override.%s.%s%s" % (override_suite, cname, suffix))

                output_file = utils.open_file(filename, 'w')
                do_list(output_file, suite, component, otype, session)
                output_file.close()

################################################################################

if __name__ == '__main__':
    main()
