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
import daklib.database as database
import daklib.queue as queue
import daklib.utils as utils

# Globals
Cnf = None
Options = None
Upload = None
projectB = None
sources = set()


################################################################################
################################################################################
################################################################################

def html_header(name, filestoexamine):
    if name.endswith('.changes'):
        name = ' '.join(name.split('_')[:2])
    print """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="de" lang="de">
  <head>
    <meta http-equiv="content-type" content="text/xhtml+xml; charset=utf-8"
    />
    <title>%(name)s - Debian NEW package overview</title>
    <link type="text/css" rel="stylesheet" href="/style.css" />
    <link rel="shortcut icon" href="http://www.debian.org/favicon.ico" />
    <script type="text/javascript">
      //<![CDATA[
      <!--
      function toggle(id, initial, display) {
        var o = document.getElementById(id);
        toggleObj(o, initial, display);
      }
      function show(id, display) {
        var o = document.getElementById(id);
        o.style.display = 'table-row-group';
      }
      function toggleObj(o, initial, display) {
        if(! o.style.display)
          o.style.display = initial;
        if(o.style.display == display) {
          o.style.display = "none";
        } else {
          o.style.display = display;
        }
      }
      //-->
      //]]>
    </script>
  </head>
  <body id="NEW-details-page">
    <div id="logo">
      <a href="http://www.debian.org/">
        <img src="http://www.debian.org/logos/openlogo-nd-50.png"
        alt="debian logo" /></a>
      <a href="http://www.debian.org/">
        <img src="http://www.debian.org/Pics/debian.png"
        alt="Debian Project" /></a>
    </div>
    <div id="titleblock">
      <img src="http://www.debian.org/Pics/red-upperleft.png"
      id="red-upperleft" alt="corner image"/>
      <img src="http://www.debian.org/Pics/red-lowerleft.png"
      id="red-lowerleft" alt="corner image"/>
      <img src="http://www.debian.org/Pics/red-upperright.png"
      id="red-upperright" alt="corner image"/>
      <img src="http://www.debian.org/Pics/red-lowerright.png"
      id="red-lowerright" alt="corner image"/>
      <span class="title">
        Debian NEW package overview for %(name)s
      </span>
    </div>
    """%{"name":name}

    # we assume only one source (.dsc) per changes here
    print """
    <div id="menu">
      <p class="title">Navigation</p>
      <p><a href="#changes" onclick="show('changes-body')">.changes</a></p>
      <p><a href="#dsc" onclick="show('dsc-body')">.dsc</a></p>
      <p><a href="#source-lintian" onclick="show('source-lintian-body')">source lintian</a></p>
      """
    for fn in filter(lambda x: x.endswith('.deb') or x.endswith('.udeb'),filestoexamine):
        packagename = fn.split('_')[0]
        print """
        <p class="subtitle">%(pkg)s</p>
        <p><a href="#binary-%(pkg)s-control" onclick="show('binary-%(pkg)s-control-body')">control file</a></p>
        <p><a href="#binary-%(pkg)s-lintian" onclick="show('binary-%(pkg)s-lintian-body')">binary lintian</a></p>
        <p><a href="#binary-%(pkg)s-contents" onclick="show('binary-%(pkg)s-contents-body')">.deb contents</a></p>
        <p><a href="#binary-%(pkg)s-copyright" onclick="show('binary-%(pkg)s-copyright-body')">copyright</a></p>
        <p><a href="#binary-%(pkg)s-file-listing" onclick="show('binary-%(pkg)s-file-listing-body')">file listing</a></p>
        """%{"pkg":packagename}
    print "    </div>"

def html_footer():
    print """    <p class="validate">Timestamp: %s (UTC)</p>"""% (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    print """    <p><a href="http://validator.w3.org/check?uri=referer">
      <img src="http://www.w3.org/Icons/valid-html401" alt="Valid HTML 4.01!"
      style="border: none; height: 31px; width: 88px" /></a>
    <a href="http://jigsaw.w3.org/css-validator/check/referer">
      <img src="http://jigsaw.w3.org/css-validator/images/vcss"
      alt="Valid CSS!" style="border: none; height: 31px; width: 88px" /></a>
    </p>
  </body>
</html>
"""

################################################################################


def do_pkg(changes_file):
    Upload.pkg.changes_file = changes_file
    Upload.init_vars()
    Upload.update_vars()
    files = Upload.pkg.files
    changes = Upload.pkg.changes

    changes["suite"] = copy.copy(changes["distribution"])

    # Find out what's new
    new = queue.determine_new(changes, files, projectB, 0)

    stdout_fd = sys.stdout

    htmlname = changes["source"] + "_" + changes["version"] + ".html"
    sources.add(htmlname)
    # do not generate html output if that source/version already has one.
    if not os.path.exists(os.path.join(Cnf["Show-New::HTMLPath"],htmlname)):
        sys.stdout = open(os.path.join(Cnf["Show-New::HTMLPath"],htmlname),"w")

        filestoexamine = []
        for pkg in new.keys():
            for fn in new[pkg]["files"]:
                if ( files[fn].has_key("new") and not
                     files[fn]["type"] in [ "orig.tar.gz", "orig.tar.bz2", "tar.gz", "tar.bz2", "diff.gz", "diff.bz2"] ):
                    filestoexamine.append(fn)

        html_header(changes["source"], filestoexamine)

        queue.check_valid(new)
        examine_package.display_changes(Upload.pkg.changes_file)

        for fn in filter(lambda fn: fn.endswith(".dsc"), filestoexamine):
            examine_package.check_dsc(fn)
        for fn in filter(lambda fn: fn.endswith(".deb") or fn.endswith(".udeb"), filestoexamine):
            examine_package.check_deb(fn)

        html_footer()
        if sys.stdout != stdout_fd:
            sys.stdout.close()
            sys.stdout = stdout_fd

################################################################################

def usage (exit_code=0):
    print """Usage: dak show-new [OPTION]... [CHANGES]...
  -h, --help                show this help and exit.
  -p, --html-path [path]    override output directory.
  """
    sys.exit(exit_code)

################################################################################

def init():
    global Cnf, Options, Upload, projectB

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Show-New::Options::Help"),
                 ("p","html-path","Show-New::HTMLPath","HasArg")]

    for i in ["help"]:
        if not Cnf.has_key("Show-New::Options::%s" % (i)):
            Cnf["Show-New::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Show-New::Options")

    if Options["help"]:
        usage()

    Upload = queue.Upload(Cnf)

    projectB = Upload.projectB

    return changes_files


################################################################################
################################################################################

def main():
    changes_files = init()

    examine_package.use_html=1

    for changes_file in changes_files:
        changes_file = utils.validate_changes_file_arg(changes_file, 0)
        if not changes_file:
            continue
        print "\n" + changes_file
        do_pkg (changes_file)
    files = set(os.listdir(Cnf["Show-New::HTMLPath"]))
    to_delete = filter(lambda x: x.endswith(".html"), files.difference(sources))
    for f in to_delete:
        os.remove(os.path.join(Cnf["Show-New::HTMLPath"],f))

################################################################################

if __name__ == '__main__':
    main()
