#!/usr/bin/env python

# Launch dak functionality
# Copyright (c) 2005 Anthony Towns <ajt@debian.org>
# $Id: dak,v 1.1 2005-11-17 08:47:31 ajt Exp $

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

# well I don't know where you're from but in AMERICA, there's a little
# thing called "abstinent until proven guilty."
#  -- http://harrietmiers.blogspot.com/2005/10/wow-i-feel-loved.html

# (if James had a blog, I bet I could find a funny quote in it to use!)

################################################################################

import sys

################################################################################

# maps a command name to a module name
functionality = [
    ("ls",                       "Show which suites packages are in",
				 ("madison", "main"), ["madison"]),
    ("rm",                       "Remove packages from suites", "melanie"),
                                 
    ("decode-dot-dak",           "Display contents of a .katie file", "ashley"),
    ("override",                 "Query/change the overrides", "alicia"),

    ("install",                  "Install a package from accepted (security only)",
                                 "amber"),     # XXX - hmm (ajt)
    ("reject-proposed-updates",  "Manually reject from proposed-updates", "lauren"),
    ("process-new",              "Process NEW and BYHAND packages", "lisa"),

    ("control-overrides",        "Manipulate/list override entries in bulk", 
                                 "natalie"),
    ("control-suite",            "Manipulate suites in bulk", "heidi"),

    ("stats",                    "Generate stats pr0n", "saffron"),
    ("cruft-report",             "Check for obsolete or duplicated packages",
                                 "rene"),
    ("queue-report",             "Produce a report on NEW and BYHAND packages",
                                 "helena"),
    ("compare-suites",           "Show fixable discrepencies between suites",
                                 "andrea"),
    
    ("check-archive",            "Archive sanity checks", "tea"),
    ("check-overrides",          "Override cruft checks", "cindy"),
    ("check-proposed-updates",   "Dependency checking for proposed-updates", 
                                 "jeri"),

    ("examine-package",          "Show information useful for NEW processing",
                                 "fernanda"),

    ("init-db",                  "Update the database to match the conf file",
                                 "alyson"),
    ("init-dirs",                "Initial setup of the archive", "rose"),
    ("import-archive",           "Populate SQL database based from an archive tree",
                                 "neve"),

    ("poolize",                  "Move packages from dists/ to pool/", "catherine"),
    ("symlink-dists",            "Generate compatability symlinks from dists/",
                                 "claire"),

    ("process-unchecked",        "Process packages in queue/unchecked", "jennifer"),

    ("process-accepted",         "Install packages into the pool", "kelly"),
    ("generate-releases",        "Generate Release files", "ziyi"),
    ("generate-index-diffs",     "Generate .diff/Index files", "tiffani"),

    ("make-suite-file-list",     
        "Generate lists of packages per suite for apt-ftparchive", "jenna"),
    ("make-maintainers",         "Generates Maintainers file for BTS etc",
                                 "charisma"),
    ("make-overrides",           "Generates override files", "denise"),

    ("mirror-split",             "Split the pool/ by architecture groups",
                                 "billie"),

    ("clean-proposed-updates",   "Remove obsolete .changes from proposed-updates",
                                 "halle"),
    ("clean-queues",             "Clean cruft from incoming", "shania"),
    ("clean-suites",            
        "Clean unused/superseded packages from the archive", "rhona"),

    ("split-done",               "Split queue/done into a data-based hierarchy",
                                 "nina"),

    ("import-ldap-fingerprints", 
        "Syncs fingerprint and uid tables with Debian LDAP db", "emilie"),
    ("import-users-from-passwd",  
        "Sync PostgreSQL users with passwd file", "julia"),
    ("find-null-maintainers",    
        "Check for users with no packages in the archive", "rosamund"),
]

names = {}
for f in functionality:
    if isinstance(f[2], str):
        names[f[2]] = names[f[0]] = (f[2], "main")
    else:
        names[f[0]] = f[2]
	for a in f[3]: names[a] = f[2]

################################################################################

def main():
    if len(sys.argv) == 0:
        print "err, argc == 0? how is that possible?"
        sys.exit(1)
    elif len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "--help"):
        print "Sub commands:"
        for f in functionality:
	    print "  %-23s %s" % (f[0], f[1])
        sys.exit(0)
    else:
        # should set PATH based on sys.argv[0] maybe
        # possibly should set names based on sys.argv[0] too
        sys.path = [sys.path[0]+"/py-symlinks"] + sys.path

        cmdname = sys.argv[0]
        cmdname = cmdname[cmdname.rfind("/")+1:]
	if cmdname in names:
            pass # invoke directly
	else:
	    cmdname = sys.argv[1]
            sys.argv = [sys.argv[0] + " " + sys.argv[1]] + sys.argv[2:]
            if cmdname not in names:
	        match = []
		for f in names:
		    if f.startswith(cmdname):
		        match.append(f)
		if len(match) == 1:
		    cmdname = match[0]
                elif len(match) > 1:
		    print "ambiguous command: %s" % ", ".join(match)
                    sys.exit(1)
		else:
                    print "unknown command \"%s\"" % (cmdname)
                    sys.exit(1)

        func = names[cmdname]
        x = __import__(func[0])
        x.__getattribute__(func[1])()

if __name__ == "__main__":
    main()

