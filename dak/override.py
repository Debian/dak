#!/usr/bin/env python

# Microscopic modification and query tool for overrides in projectb
# Copyright (C) 2004, 2006  Daniel Silverstone <dsilvers@digital-scurf.org>

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
## So line up your soldiers and she'll shoot them all down
## Coz Alisha Rules The World
## You think you found a dream, then it shatters and it seems,
## That Alisha Rules The World
################################################################################

import pg, sys
import apt_pkg
from daklib import logging
from daklib import database
from daklib import utils

################################################################################

Cnf = None
projectB = None

################################################################################

# Shamelessly stolen from 'dak rm'. Should probably end up in utils.py
def game_over():
    answer = utils.our_raw_input("Continue (y/N)? ").lower()
    if answer != "y":
        print "Aborted."
        sys.exit(1)


def usage (exit_code=0):
    print """Usage: dak override [OPTIONS] package [section] [priority]
Make microchanges or microqueries of the binary overrides

  -h, --help                 show this help and exit
  -d, --done=BUG#            send priority/section change as closure to bug#
  -n, --no-action            don't do anything
  -s, --suite                specify the suite to use
"""
    sys.exit(exit_code)

def main ():
    global Cnf, projectB

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Override::Options::Help"),
                 ('d',"done","Override::Options::Done", "HasArg"),
                 ('n',"no-action","Override::Options::No-Action"),
                 ('s',"suite","Override::Options::Suite", "HasArg"),
                 ]
    for i in ["help", "no-action"]:
        if not Cnf.has_key("Override::Options::%s" % (i)):
            Cnf["Override::Options::%s" % (i)] = ""
    if not Cnf.has_key("Override::Options::Suite"):
        Cnf["Override::Options::Suite"] = "unstable"

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Override::Options")

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    if not arguments:
        utils.fubar("package name is a required argument.")

    package = arguments.pop(0)
    suite = Options["Suite"]
    if arguments and len(arguments) > 2:
        utils.fubar("Too many arguments")

    if arguments and len(arguments) == 1:
        # Determine if the argument is a priority or a section...
        arg = arguments.pop()
        q = projectB.query("""
        SELECT ( SELECT COUNT(*) FROM section WHERE section=%s ) AS secs,
               ( SELECT COUNT(*) FROM priority WHERE priority=%s ) AS prios
               """ % ( pg._quote(arg,"str"), pg._quote(arg,"str")))
        r = q.getresult()
        if r[0][0] == 1:
            arguments = (arg,".")
        elif r[0][1] == 1:
            arguments = (".",arg)
        else:
            utils.fubar("%s is not a valid section or priority" % (arg))

    # Retrieve current section/priority...
    oldsection, oldsourcesection, oldpriority = None, None, None
    for type in ['source', 'binary']:
        eqdsc = '!='
        if type == 'source':
            eqdsc = '='
        q = projectB.query("""
    SELECT priority.priority AS prio, section.section AS sect, override_type.type AS type
      FROM override, priority, section, suite, override_type
     WHERE override.priority = priority.id
       AND override.type = override_type.id
       AND override_type.type %s 'dsc'
       AND override.section = section.id
       AND override.package = %s
       AND override.suite = suite.id
       AND suite.suite_name = %s
        """ % (eqdsc, pg._quote(package,"str"), pg._quote(suite,"str")))

        if q.ntuples() == 0:
            continue
        if q.ntuples() > 1:
            utils.fubar("%s is ambiguous. Matches %d packages" % (package,q.ntuples()))

        r = q.getresult()
        if type == 'binary':
            oldsection = r[0][1]
            oldpriority = r[0][0]
        else:
            oldsourcesection = r[0][1]
            oldpriority = 'source'

    if not oldpriority and not oldsourcesection:
        utils.fubar("Unable to find package %s" % (package))
    if oldsection and oldsourcesection and oldsection != oldsourcesection:
        # When setting overrides, both source & binary will become the same section
        utils.warn("Source is in section '%s' instead of '%s'" % (oldsourcesection, oldsection))
    if not oldsection:
        oldsection = oldsourcesection

    if not arguments:
        print "%s is in section '%s' at priority '%s'" % (
            package,oldsection,oldpriority)
        sys.exit(0)

    # At this point, we have a new section and priority... check they're valid...
    newsection, newpriority = arguments

    if newsection == ".":
        newsection = oldsection
    if newpriority == ".":
        newpriority = oldpriority

    q = projectB.query("SELECT id FROM section WHERE section=%s" % (
        pg._quote(newsection,"str")))

    if q.ntuples() == 0:
        utils.fubar("Supplied section %s is invalid" % (newsection))
    newsecid = q.getresult()[0][0]

    q = projectB.query("SELECT id FROM priority WHERE priority=%s" % (
        pg._quote(newpriority,"str")))

    if q.ntuples() == 0:
        utils.fubar("Supplied priority %s is invalid" % (newpriority))
    newprioid = q.getresult()[0][0]

    if newpriority == oldpriority and newsection == oldsection:
        print "I: Doing nothing"
        sys.exit(0)

    if oldpriority == 'source' and newpriority != 'source':
        utils.fubar("Trying to change priority of a source-only package")

    # If we're in no-action mode
    if Options["No-Action"]:
        if newpriority != oldpriority:
            print "I: Would change priority from %s to %s" % (oldpriority,newpriority)
        if newsection != oldsection:
            print "I: Would change section from %s to %s" % (oldsection,newsection)
        if Options.has_key("Done"):
            print "I: Would also close bug(s): %s" % (Options["Done"])

        sys.exit(0)

    if newpriority != oldpriority:
        print "I: Will change priority from %s to %s" % (oldpriority,newpriority)
    if newsection != oldsection:
        print "I: Will change section from %s to %s" % (oldsection,newsection)

    if not Options.has_key("Done"):
        pass
        #utils.warn("No bugs to close have been specified. Noone will know you have done this.")
    else:
        print "I: Will close bug(s): %s" % (Options["Done"])

    game_over()

    Logger = logging.Logger(Cnf, "override")

    projectB.query("BEGIN WORK")
    # We're in "do it" mode, we have something to do... do it
    if newpriority != oldpriority:
        q = projectB.query("""
        UPDATE override
           SET priority=%d
         WHERE package=%s
           AND override.type != %d
           AND suite = (SELECT id FROM suite WHERE suite_name=%s)""" % (
            newprioid,
            pg._quote(package,"str"), database.get_override_type_id("dsc"),
            pg._quote(suite,"str") ))
        Logger.log(["changed priority",package,oldpriority,newpriority])

    if newsection != oldsection:
        q = projectB.query("""
        UPDATE override
           SET section=%d
         WHERE package=%s
           AND suite = (SELECT id FROM suite WHERE suite_name=%s)""" % (
            newsecid,
            pg._quote(package,"str"),
            pg._quote(suite,"str") ))
        Logger.log(["changed section",package,oldsection,newsection])
    projectB.query("COMMIT WORK")

    if Options.has_key("Done"):
        Subst = {}
        Subst["__OVERRIDE_ADDRESS__"] = Cnf["Override::MyEmailAddress"]
        Subst["__BUG_SERVER__"] = Cnf["Dinstall::BugServer"]
        bcc = []
        if Cnf.Find("Dinstall::Bcc") != "":
            bcc.append(Cnf["Dinstall::Bcc"])
        if Cnf.Find("Override::Bcc") != "":
            bcc.append(Cnf["Override::Bcc"])
        if bcc:
            Subst["__BCC__"] = "Bcc: " + ", ".join(bcc)
        else:
            Subst["__BCC__"] = "X-Filler: 42"
        Subst["__CC__"] = "X-DAK: dak override\nX-Katie: alicia"
        Subst["__ADMIN_ADDRESS__"] = Cnf["Dinstall::MyAdminAddress"]
        Subst["__DISTRO__"] = Cnf["Dinstall::MyDistribution"]
        Subst["__WHOAMI__"] = utils.whoami()
        Subst["__SOURCE__"] = package

        summary = "Concerning package %s...\n" % (package)
        summary += "Operating on the %s suite\n" % (suite)
        if newpriority != oldpriority:
            summary += "Changed priority from %s to %s\n" % (oldpriority,newpriority)
        if newsection != oldsection:
            summary += "Changed section from %s to %s\n" % (oldsection,newsection)
        Subst["__SUMMARY__"] = summary

        for bug in utils.split_args(Options["Done"]):
            Subst["__BUG_NUMBER__"] = bug
            mail_message = utils.TemplateSubst(
                Subst,Cnf["Dir::Templates"]+"/override.bug-close")
            utils.send_mail(mail_message)
            Logger.log(["closed bug",bug])

    Logger.close()

    print "Done"

#################################################################################

if __name__ == '__main__':
    main()
