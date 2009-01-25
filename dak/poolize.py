#!/usr/bin/env python

""" Poolify (move packages from "legacy" type locations to pool locations) """
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# "Welcome to where time stands still,
#  No one leaves and no one will."
#   - Sanitarium - Metallica / Master of the puppets

################################################################################

import os, pg, re, stat, sys
import apt_pkg, apt_inst
import daklib.database
import daklib.utils
from daklib.regexes import re_isadeb, re_extract_src_version, re_no_epoch, re_issource

################################################################################

Cnf = None
projectB = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak poolize [OPTIONS]
Migrate packages from legacy locations into the pool.

  -l, --limit=AMOUNT         only migrate AMOUNT Kb of packages
  -n, --no-action            don't do anything
  -v, --verbose              explain what is being done
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

# Q is a python-postgresql query result set and must have the
# following four columns:
#  o files.id (as 'files_id')
#  o files.filename
#  o location.path
#  o component.name (as 'component')
#
# limit is a value in bytes or -1 for no limit (use with care!)
# verbose and no_action are booleans

def poolize (q, limit, verbose, no_action):
    poolized_size = 0L
    poolized_count = 0

    # Parse -l/--limit argument
    qd = q.dictresult()
    for qid in qd:
        legacy_filename = qid["path"]+qid["filename"]
        size = os.stat(legacy_filename)[stat.ST_SIZE]
        if (poolized_size + size) > limit and limit >= 0:
            daklib.utils.warn("Hit %s limit." % (daklib.utils.size_type(limit)))
            break
        poolized_size += size
        poolized_count += 1
        base_filename = os.path.basename(legacy_filename)
        destination_filename = base_filename
        # Work out the source package name
        if re_isadeb.match(base_filename):
            control = apt_pkg.ParseSection(apt_inst.debExtractControl(daklib.utils.open_file(legacy_filename)))
            package = control.Find("Package", "")
            source = control.Find("Source", package)
            if source.find("(") != -1:
                m = re_extract_src_version.match(source)
                source = m.group(1)
            # If it's a binary, we need to also rename the file to include the architecture
            version = control.Find("Version", "")
            architecture = control.Find("Architecture", "")
            if package == "" or version == "" or architecture == "":
                daklib.utils.fubar("%s: couldn't determine required information to rename .deb file." % (legacy_filename))
            version = re_no_epoch.sub('', version)
            destination_filename = "%s_%s_%s.deb" % (package, version, architecture)
        else:
            m = re_issource.match(base_filename)
            if m:
                source = m.group(1)
            else:
                daklib.utils.fubar("expansion of source filename '%s' failed." % (legacy_filename))
        # Work out the component name
        component = qid["component"]
        if component == "":
            q = projectB.query("SELECT DISTINCT(c.name) FROM override o, component c WHERE o.package = '%s' AND o.component = c.id;" % (source))
            ql = q.getresult()
            if not ql:
                daklib.utils.fubar("No override match for '%s' so I can't work out the component." % (source))
            if len(ql) > 1:
                daklib.utils.fubar("Multiple override matches for '%s' so I can't work out the component." % (source))
            component = ql[0][0]
        # Work out the new location
        q = projectB.query("SELECT l.id FROM location l, component c WHERE c.name = '%s' AND c.id = l.component AND l.type = 'pool';" % (component))
        ql = q.getresult()
        if len(ql) != 1:
            daklib.utils.fubar("couldn't determine location ID for '%s'. [query returned %d matches, not 1 as expected]" % (source, len(ql)))
        location_id = ql[0][0]
        # First move the files to the new location
        pool_location = daklib.utils.poolify (source, component)
        pool_filename = pool_location + destination_filename
        destination = Cnf["Dir::Pool"] + pool_location + destination_filename
        if os.path.exists(destination):
            daklib.utils.fubar("'%s' already exists in the pool; serious FUBARity." % (legacy_filename))
        if verbose:
            print "Moving: %s -> %s" % (legacy_filename, destination)
        if not no_action:
            daklib.utils.move(legacy_filename, destination)
        # Then Update the DB's files table
        if verbose:
            print "SQL: UPDATE files SET filename = '%s', location = '%s' WHERE id = '%s'" % (pool_filename, location_id, qid["files_id"])
        if not no_action:
            q = projectB.query("UPDATE files SET filename = '%s', location = '%s' WHERE id = '%s'" % (pool_filename, location_id, qid["files_id"]))

    sys.stderr.write("Poolized %s in %s files.\n" % (daklib.utils.size_type(poolized_size), poolized_count))

################################################################################

def main ():
    global Cnf, projectB

    Cnf = daklib.utils.get_conf()

    for i in ["help", "limit", "no-action", "verbose" ]:
        if not Cnf.has_key("Poolize::Options::%s" % (i)):
            Cnf["Poolize::Options::%s" % (i)] = ""


    Arguments = [('h',"help","Poolize::Options::Help"),
                 ('l',"limit", "Poolize::Options::Limit", "HasArg"),
                 ('n',"no-action","Poolize::Options::No-Action"),
                 ('v',"verbose","Poolize::Options::Verbose")]

    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Poolize::Options")

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)

    if not Options["Limit"]:
        limit = -1
    else:
        limit = int(Options["Limit"]) * 1024

    # -n/--no-action implies -v/--verbose
    if Options["No-Action"]:
        Options["Verbose"] = "true"

    # Sanity check the limit argument
    if limit > 0 and limit < 1024:
        daklib.utils.fubar("-l/--limit takes an argument with a value in kilobytes.")

    # Grab a list of all files not already in the pool
    q = projectB.query("""
SELECT l.path, f.filename, f.id as files_id, c.name as component
   FROM files f, location l, component c WHERE
    NOT EXISTS (SELECT 1 FROM location l WHERE l.type = 'pool' AND f.location = l.id)
    AND NOT (f.filename ~ '^potato') AND f.location = l.id AND l.component = c.id
UNION SELECT l.path, f.filename, f.id as files_id, null as component
   FROM files f, location l WHERE
    NOT EXISTS (SELECT 1 FROM location l WHERE l.type = 'pool' AND f.location = l.id)
    AND NOT (f.filename ~ '^potato') AND f.location = l.id AND NOT EXISTS
     (SELECT 1 FROM location l WHERE l.component IS NOT NULL AND f.location = l.id);""")

    poolize(q, limit, Options["Verbose"], Options["No-Action"])

#######################################################################################

if __name__ == '__main__':
    main()
