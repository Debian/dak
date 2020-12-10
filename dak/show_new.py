#! /usr/bin/env python3

""" Output html for packages in NEW """
# Copyright (C) 2007, 2009 Joerg Jaspert <joerg@debian.org>

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

import os
import sys
import time
import apt_pkg
import dak.examine_package

from daklib import policy
from daklib.dbconn import *
from daklib.config import Config
from daklib.dakmultiprocessing import DakProcessPool, PROC_STATUS_SUCCESS, PROC_STATUS_EXCEPTION
from multiprocessing import Manager

# Globals
Cnf = None
Options = None
manager = Manager()
sources = manager.list()
htmlfiles_to_process = manager.list()
timeout_str = "Error or timeout while processing"


################################################################################
################################################################################
################################################################################

def html_header(name, missing):
    if name.endswith('.changes'):
        name = ' '.join(name.split('_')[:2])
    result = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>%(name)s - Debian NEW package overview</title>
    <link type="text/css" rel="stylesheet" href="/style.css" />
    <link rel="shortcut icon" href="https://www.debian.org/favicon.ico" />
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
      <a href="https://www.debian.org/">
        <img src="https://www.debian.org/logos/openlogo-nd-50.png"
        alt="" /></a>
      <a href="https://www.debian.org/">
        <img src="https://www.debian.org/Pics/debian.png"
        alt="Debian Project" /></a>
    </div>
    <div id="titleblock">
      <img src="https://www.debian.org/Pics/red-upperleft.png"
      id="red-upperleft" alt=""/>
      <img src="https://www.debian.org/Pics/red-lowerleft.png"
      id="red-lowerleft" alt=""/>
      <img src="https://www.debian.org/Pics/red-upperright.png"
      id="red-upperright" alt=""/>
      <img src="https://www.debian.org/Pics/red-lowerright.png"
      id="red-lowerright" alt=""/>
      <span class="title">
        Debian NEW package overview for %(name)s
      </span>
    </div>

    """ % {"name": name}

    # we assume only one source (.dsc) per changes here
    result += """
    <div id="menu">
      <p class="title">Navigation</p>
      <p><a href="#changes" onclick="show('changes-body')">.changes</a></p>
      <p><a href="#dsc" onclick="show('dsc-body')">.dsc</a></p>
      <p><a href="#source-lintian" onclick="show('source-lintian-body')">source lintian</a></p>

"""
    for binarytype, packagename in [m for m in missing if m[0] in ('deb', 'udeb')]:
        result += """
        <p class="subtitle">%(pkg)s</p>
        <p><a href="#binary-%(pkg)s-control" onclick="show('binary-%(pkg)s-control-body')">control file</a></p>
        <p><a href="#binary-%(pkg)s-lintian" onclick="show('binary-%(pkg)s-lintian-body')">binary lintian</a></p>
        <p><a href="#binary-%(pkg)s-contents" onclick="show('binary-%(pkg)s-contents-body')">.deb contents</a></p>
        <p><a href="#binary-%(pkg)s-copyright" onclick="show('binary-%(pkg)s-copyright-body')">copyright</a></p>
        <p><a href="#binary-%(pkg)s-file-listing" onclick="show('binary-%(pkg)s-file-listing-body')">file listing</a></p>

""" % {"pkg": packagename}
    result += "    </div>"
    return result


def html_footer():
    result = """    <p class="validate">Timestamp: %s (UTC)</p>
""" % (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    result += "</body></html>"
    return result

################################################################################


def do_pkg(upload_id):
    cnf = Config()

    session = DBConn().session()
    upload = session.query(PolicyQueueUpload).filter_by(id=upload_id).one()

    queue = upload.policy_queue
    changes = upload.changes

    origchanges = os.path.join(queue.path, changes.changesname)
    print(origchanges)

    htmlname = "{0}_{1}.html".format(changes.source, changes.version)
    htmlfile = os.path.join(cnf['Show-New::HTMLPath'], htmlname)

    # Have we already processed this?
    if os.path.exists(htmlfile) and \
        os.stat(htmlfile).st_mtime > time.mktime(changes.created.timetuple()):
        with open(htmlfile, "r") as fd:
            if fd.read() != timeout_str:
                sources.append(htmlname)
                return (PROC_STATUS_SUCCESS,
                        '%s already up-to-date' % htmlfile)

    # Go, process it... Now!
    htmlfiles_to_process.append(htmlfile)
    sources.append(htmlname)

    group = cnf.get('Dinstall::UnprivGroup') or None

    with open(htmlfile, 'w') as outfile, \
            policy.UploadCopy(upload, group=group) as upload_copy:
        handler = policy.PolicyQueueUploadHandler(upload, session)
        missing = [(o['type'], o['package']) for o in handler.missing_overrides()]
        distribution = changes.distribution

        outfile.write(html_header(changes.source, missing))
        outfile.write(dak.examine_package.display_changes(distribution, origchanges))

        if upload.source is not None and ('dsc', upload.source.source) in missing:
            fn = os.path.join(upload_copy.directory, upload.source.poolfile.basename)
            outfile.write(dak.examine_package.check_dsc(distribution, fn, session))
        for binary in upload.binaries:
            if (binary.binarytype, binary.package) not in missing:
                continue
            fn = os.path.join(upload_copy.directory, binary.poolfile.basename)
            outfile.write(dak.examine_package.check_deb(distribution, fn, session))

        outfile.write(html_footer())

    session.close()
    htmlfiles_to_process.remove(htmlfile)
    return (PROC_STATUS_SUCCESS, '{0} already updated'.format(htmlfile))

################################################################################


def usage(exit_code=0):
    print("""Usage: dak show-new [OPTION]... [CHANGES]...
  -h, --help                show this help and exit.
  -p, --html-path [path]    override output directory.
  """)
    sys.exit(exit_code)

################################################################################


def init(session):
    global cnf, Options

    cnf = Config()

    Arguments = [('h', "help", "Show-New::Options::Help"),
                 ("p", "html-path", "Show-New::HTMLPath", "HasArg"),
                 ('q', 'queue', 'Show-New::Options::Queue', 'HasArg')]

    for i in ["help"]:
        key = "Show-New::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    changesnames = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Show-New::Options")

    if Options["help"]:
        usage()

    queue_names = Options.find('Queue', 'new').split(',')
    uploads = session.query(PolicyQueueUpload) \
        .join(PolicyQueueUpload.policy_queue).filter(PolicyQueue.queue_name.in_(queue_names)) \
        .join(PolicyQueueUpload.changes).order_by(DBChange.source)

    if len(changesnames) > 0:
        uploads = uploads.filter(DBChange.changesname.in_(changesnames))

    return uploads


def result_callback(r):
    code, msg = r
    if code == PROC_STATUS_EXCEPTION:
        print("Job raised exception: %s" % (msg))
    elif code != PROC_STATUS_SUCCESS:
        print("Job failed: %s" % (msg))


################################################################################
################################################################################

def main():
    dak.examine_package.use_html = True
    pool = DakProcessPool(processes=5)

    session = DBConn().session()
    upload_ids = [u.id for u in init(session)]
    session.close()

    for upload_id in upload_ids:
        pool.apply_async(do_pkg, [upload_id], callback=result_callback)
    pool.close()

    pool.join()

    for htmlfile in htmlfiles_to_process:
        with open(htmlfile, "w") as fd:
            fd.write(timeout_str)

    if pool.overall_status() != PROC_STATUS_SUCCESS:
        raise Exception("Processing failed (code %s)" % (pool.overall_status()))

    files = set(os.listdir(cnf["Show-New::HTMLPath"]))
    to_delete = [x for x in files.difference(set(sources)) if x.endswith(".html")]
    for f in to_delete:
        os.remove(os.path.join(cnf["Show-New::HTMLPath"], f))

################################################################################


if __name__ == '__main__':
    main()
