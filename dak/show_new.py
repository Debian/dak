#!/usr/bin/env python

# Output html for packages in NEW
# Copyright (C) 2007 Joerg Jaspert <joerg@debian.org>

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

# <elmo> I'm James Troup, long term source of all evil in Debian. you may
#        know me from such debian-devel-announce gems as "Serious
#        Problems With ...."

################################################################################

import copy, os, sys, time
import apt_pkg
import examine_package
import daklib.database
import daklib.queue
import daklib.utils

# Globals
Cnf = None
Options = None
Upload = None
projectB = None
sources = set()


################################################################################
################################################################################
################################################################################

def html_header(name):
    if name.endswith('.changes'):
        name = ' '.join(name.split('_')[:2])
    print """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
        <html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">"""
    print "<title>%s - Debian NEW package overview</title>" % (name)
    print """<link type="text/css" rel="stylesheet" href="/style.css">
        <link rel="shortcut icon" href="http://www.debian.org/favicon.ico">
        </head>
        <body>
        <div align="center">
        <a href="http://www.debian.org/">
     <img src="http://www.debian.org/logos/openlogo-nd-50.png" border="0" hspace="0" vspace="0" alt=""></a>
        <a href="http://www.debian.org/">
     <img src="http://www.debian.org/Pics/debian.png" border="0" hspace="0" vspace="0" alt="Debian Project"></a>
        </div>
        <br />
        <table class="reddy" width="100%">
        <tr>
        <td class="reddy">
    <img src="http://www.debian.org/Pics/red-upperleft.png" align="left" border="0" hspace="0" vspace="0"
     alt="" width="15" height="16"></td>"""
    print """<td rowspan="2" class="reddy">Debian NEW package overview for %s</td>""" % (name)
    print """<td class="reddy">
    <img src="http://www.debian.org/Pics/red-upperright.png" align="right" border="0" hspace="0" vspace="0"
     alt="" width="16" height="16"></td>
        </tr>
        <tr>
        <td class="reddy">
    <img src="http://www.debian.org/Pics/red-lowerleft.png" align="left" border="0" hspace="0" vspace="0"
     alt="" width="16" height="16"></td>
        <td class="reddy">
    <img src="http://www.debian.org/Pics/red-lowerright.png" align="right" border="0" hspace="0" vspace="0"
     alt="" width="15" height="16"></td>
        </tr>
        </table>
        """

def html_footer():
    print "<p class=\"validate\">Timestamp: %s (UTC)</p>" % (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    print """<a href="http://validator.w3.org/check?uri=referer">
    <img border="0" src="http://www.w3.org/Icons/valid-html401" alt="Valid HTML 4.01!" height="31" width="88"></a>
        <a href="http://jigsaw.w3.org/css-validator/check/referer">
    <img border="0" src="http://jigsaw.w3.org/css-validator/images/vcss" alt="Valid CSS!"
     height="31" width="88"></a>
    """
    print "</body></html>"


################################################################################


def do_pkg(changes_file):
    Upload.pkg.changes_file = changes_file
    Upload.init_vars()
    Upload.update_vars()
    files = Upload.pkg.files
    changes = Upload.pkg.changes

    changes["suite"] = copy.copy(changes["distribution"])

    # Find out what's new
    new = daklib.queue.determine_new(changes, files, projectB, 0)

    stdout_fd = sys.stdout

    htmlname = changes["source"] + "_" + changes["version"] + ".html"
    sources.add(htmlname)
    # do not generate html output if that source/version already has one.
    if not os.path.exists(os.path.join(Cnf["Show-New::HTMLPath"],htmlname)):
        sys.stdout = open(os.path.join(Cnf["Show-New::HTMLPath"],htmlname),"w")
        html_header(changes["source"])

        daklib.queue.check_valid(new)
        examine_package.display_changes(Upload.pkg.changes_file)

        for pkg in new.keys():
            for file in new[pkg]["files"]:
                if ( files[file].has_key("new") and not
                     files[file]["type"] in [ "orig.tar.gz", "orig.tar.bz2", "tar.gz", "tar.bz2", "diff.gz", "diff.bz2"] ):
                    if file.endswith(".deb") or file.endswith(".udeb"):
                        examine_package.check_deb(file)
                    elif file.endswith(".dsc"):
                        examine_package.check_dsc(file)

        html_footer()
        if sys.stdout != stdout_fd:
            sys.stdout.close()
            sys.stdout = stdout_fd

################################################################################

def usage (exit_code=0):
    print """Usage: dak show-new [OPTION]... [CHANGES]...
  -h, --help                show this help and exit.
  """
    sys.exit(exit_code)

################################################################################

def init():
    global Cnf, Options, Upload, projectB

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Show-New::Options::Help")]

    for i in ["help"]:
        if not Cnf.has_key("Show-New::Options::%s" % (i)):
            Cnf["Show-New::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Show-New::Options")

    if Options["help"]:
        usage()

    Upload = daklib.queue.Upload(Cnf)

    projectB = Upload.projectB

    return changes_files


################################################################################
################################################################################

def main():
    changes_files = init()

    examine_package.use_html=1

    for changes_file in changes_files:
        changes_file = daklib.utils.validate_changes_file_arg(changes_file, 0)
        if not changes_file:
            continue
        print "\n" + changes_file
        do_pkg (changes_file)
    files = set(os.listdir(Cnf["Show-New::HTMLPath"]))
    to_delete = files.difference(sources)
    for file in to_delete:
        os.remove(os.path.join(Cnf["Show-New::HTMLPath"],file))

################################################################################

if __name__ == '__main__':
    main()
