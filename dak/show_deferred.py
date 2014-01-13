#!/usr/bin/env python

""" Overview of the DEFERRED queue, based on queue-report """
#    Copyright (C) 2001, 2002, 2003, 2005, 2006  James Troup <james@nocrew.org>
# Copyright (C) 2008 Thomas Viehmann <tv@beamnet.de>

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

import sys, os, re, time
import apt_pkg
import rrdtool

from debian import deb822

from daklib.dbconn import *
from daklib.gpg import SignedFile
from daklib import utils
from daklib.regexes import re_html_escaping, html_escaping

################################################################################
### work around bug #487902 in debian-python 0.1.10
deb822.Changes._multivalued_fields = {
            "files": [ "md5sum", "size", "section", "priority", "name" ],
            "checksums-sha1": ["sha1", "size", "name"],
            "checksums-sha256": ["sha256", "size", "name"],
          }

################################################################################

row_number = 1

def html_escape(s):
    return re_html_escaping.sub(lambda x: html_escaping.get(x.group(0)), s)

################################################################################

def header():
  return  """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
        <html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <title>Deferred uploads to Debian</title>
        <link type="text/css" rel="stylesheet" href="style.css">
        <link rel="shortcut icon" href="https://www.debian.org/favicon.ico">
        </head>
        <body>
        <div align="center">
        <a href="https://www.debian.org/">
     <img src="https://www.debian.org/logos/openlogo-nd-50.png" border="0" hspace="0" vspace="0" alt=""></a>
        <a href="https://www.debian.org/">
     <img src="https://www.debian.org/Pics/debian.png" border="0" hspace="0" vspace="0" alt="Debian Project"></a>
        </div>
        <br />
        <table class="reddy" width="100%">
        <tr>
        <td class="reddy">
    <img src="https://www.debian.org/Pics/red-upperleft.png" align="left" border="0" hspace="0" vspace="0"
     alt="" width="15" height="16"></td>
        <td rowspan="2" class="reddy">Deferred uploads to Debian</td>
        <td class="reddy">
    <img src="https://www.debian.org/Pics/red-upperright.png" align="right" border="0" hspace="0" vspace="0"
     alt="" width="16" height="16"></td>
        </tr>
        <tr>
        <td class="reddy">
    <img src="https://www.debian.org/Pics/red-lowerleft.png" align="left" border="0" hspace="0" vspace="0"
     alt="" width="16" height="16"></td>
        <td class="reddy">
    <img src="https://www.debian.org/Pics/red-lowerright.png" align="right" border="0" hspace="0" vspace="0"
     alt="" width="15" height="16"></td>
        </tr>
        </table>
        """

def footer():
    res = "<p class=\"validate\">Timestamp: %s (UTC)</p>" % (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    res += "<p class=\"timestamp\">There are <a href=\"/stat.html\">graphs about the queues</a> available.</p>"
    res += "</body></html>"
    return res.encode('utf-8')

def table_header():
    return """<h1>Deferred uploads</h1>
      <center><table border="0">
        <tr>
          <th align="center">Change</th>
          <th align="center">Time remaining</th>
          <th align="center">Uploader</th>
          <th align="center">Closes</th>
        </tr>
        """

def table_footer():
    return '</table><br/><p>non-NEW uploads are <a href="/deferred/">available</a>, see the <a href="ftp://ftp-master.debian.org/pub/UploadQueue/README">UploadQueue-README</a> for more information.</p></center><br/>\n'

def table_row(changesname, delay, changed_by, closes, fingerprint):
    global row_number

    res = '<tr class="%s">'%((row_number%2) and 'odd' or 'even')
    res += (2*'<td valign="top">%s</td>')%tuple(map(html_escape,(changesname,delay)))
    res += '<td valign="top">%s<br><span class=\"deferredfp\">Fingerprint: %s</span></td>' % (html_escape(changed_by), fingerprint)
    res += ('<td valign="top">%s</td>' %
             ''.join(map(lambda close:  '<a href="https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=%s">#%s</a><br>' % (close, close),closes)))
    res += '</tr>\n'
    row_number+=1
    return res

def update_graph_database(rrd_dir, *counts):
    if not rrd_dir:
        return

    rrd_file = os.path.join(rrd_dir, 'deferred.rrd')
    counts = [str(count) for count in counts]
    update = [rrd_file, "N:"+":".join(counts)]

    try:
        rrdtool.update(*update)
    except rrdtool.error:
        create = [rrd_file]+"""
--step
300
--start
0
DS:day0:GAUGE:7200:0:1000
DS:day1:GAUGE:7200:0:1000
DS:day2:GAUGE:7200:0:1000
DS:day3:GAUGE:7200:0:1000
DS:day4:GAUGE:7200:0:1000
DS:day5:GAUGE:7200:0:1000
DS:day6:GAUGE:7200:0:1000
DS:day7:GAUGE:7200:0:1000
DS:day8:GAUGE:7200:0:1000
DS:day9:GAUGE:7200:0:1000
DS:day10:GAUGE:7200:0:1000
DS:day11:GAUGE:7200:0:1000
DS:day12:GAUGE:7200:0:1000
DS:day13:GAUGE:7200:0:1000
DS:day14:GAUGE:7200:0:1000
DS:day15:GAUGE:7200:0:1000
RRA:AVERAGE:0.5:1:599
RRA:AVERAGE:0.5:6:700
RRA:AVERAGE:0.5:24:775
RRA:AVERAGE:0.5:288:795
RRA:MIN:0.5:1:600
RRA:MIN:0.5:6:700
RRA:MIN:0.5:24:775
RRA:MIN:0.5:288:795
RRA:MAX:0.5:1:600
RRA:MAX:0.5:6:700
RRA:MAX:0.5:24:775
RRA:MAX:0.5:288:795
""".strip().split("\n")
        try:
            rc = rrdtool.create(*create)
            ru = rrdtool.update(*update)
        except rrdtool.error as e:
            print('warning: queue_report: rrdtool error, skipping %s.rrd: %s' % (type, e))
    except NameError:
        pass

def get_upload_data(changesfn):
    achanges = deb822.Changes(file(changesfn))
    changesname = os.path.basename(changesfn)
    delay = os.path.basename(os.path.dirname(changesfn))
    m = re.match(r'([0-9]+)-day', delay)
    if m:
        delaydays = int(m.group(1))
        remainingtime = (delaydays>0)*max(0,24*60*60+os.stat(changesfn).st_mtime-time.time())
        delay = "%d days %02d:%02d" %(max(delaydays-1,0), int(remainingtime/3600),int(remainingtime/60)%60)
    else:
        delaydays = 0
        remainingtime = 0

    uploader = achanges.get('changed-by')
    uploader = re.sub(r'^\s*(\S.*)\s+<.*>',r'\1',uploader)
    with utils.open_file(changesfn) as f:
        fingerprint = SignedFile(f.read(), keyrings=get_active_keyring_paths()).fingerprint
    if Cnf.has_key("Show-Deferred::LinkPath"):
        isnew = 0
        suites = get_suites_source_in(achanges['source'])
        if 'unstable' not in suites and 'experimental' not in suites:
            isnew = 1

        for b in achanges['binary'].split():
            suites = get_suites_binary_in(b)
            if 'unstable' not in suites and 'experimental' not in suites:
                isnew = 1

        if not isnew:
            # we don't link .changes because we don't want other people to
            # upload it with the existing signature.
            for afn in map(lambda x: x['name'],achanges['files']):
                lfn = os.path.join(Cnf["Show-Deferred::LinkPath"],afn)
                qfn = os.path.join(os.path.dirname(changesfn),afn)
                if os.path.islink(lfn):
                    os.unlink(lfn)
                if os.path.exists(qfn):
                    os.symlink(qfn,lfn)
                    os.chmod(qfn, 0o644)
    return (max(delaydays-1,0)*24*60*60+remainingtime, changesname, delay, uploader, achanges.get('closes','').split(), fingerprint, achanges, delaydays)

def list_uploads(filelist, rrd_dir):
    uploads = map(get_upload_data, filelist)
    uploads.sort()
    # print the summary page
    print header()
    if uploads:
        print table_header()
        print ''.join(map(lambda x: table_row(*x[1:6]), uploads)).encode('utf-8')
        print table_footer()
    else:
        print '<h1>Currently no deferred uploads to Debian</h1>'
    print footer()
    # machine readable summary
    if Cnf.has_key("Show-Deferred::LinkPath"):
        fn = os.path.join(Cnf["Show-Deferred::LinkPath"],'.status.tmp')
        f = open(fn,"w")
        try:
            counts = [0]*16
            for u in uploads:
                counts[u[7]] += 1
                print >> f, "Changes-file: %s"%u[1]
                fields = """Location: DEFERRED
Delayed-Until: %s
Delay-Remaining: %s
Fingerprint: %s"""%(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time()+u[0])),u[2], u[5])
                print >> f, fields
                encoded = unicode(u[6]).encode('utf-8')
                print >> f, encoded.rstrip()
                open(os.path.join(Cnf["Show-Deferred::LinkPath"],u[1]),"w").write(encoded+fields+'\n')
                print >> f
            f.close()
            os.rename(os.path.join(Cnf["Show-Deferred::LinkPath"],'.status.tmp'),
                      os.path.join(Cnf["Show-Deferred::LinkPath"],'status'))
            update_graph_database(rrd_dir, *counts)
        except:
            os.unlink(fn)
            raise

def usage (exit_code=0):
    if exit_code:
        f = sys.stderr
    else:
        f = sys.stdout
    print >> f, """Usage: dak show-deferred
  -h, --help                    show this help and exit.
  -p, --link-path [path]        override output directory.
  -d, --deferred-queue [path]   path to the deferred queue
  -r, --rrd=key                 Directory where rrd files to be updated are stored
  """
    sys.exit(exit_code)

def init():
    global Cnf, Options
    Cnf = utils.get_conf()
    Arguments = [('h',"help","Show-Deferred::Options::Help"),
                 ("p","link-path","Show-Deferred::LinkPath","HasArg"),
                 ("d","deferred-queue","Show-Deferred::DeferredQueue","HasArg"),
                 ('r',"rrd","Show-Deferred::Options::Rrd", "HasArg")]
    args = apt_pkg.parse_commandline(Cnf,Arguments,sys.argv)
    for i in ["help"]:
        if not Cnf.has_key("Show-Deferred::Options::%s" % (i)):
            Cnf["Show-Deferred::Options::%s" % (i)] = ""
    for i,j in [("DeferredQueue","--deferred-queue")]:
        if not Cnf.has_key("Show-Deferred::%s" % (i)):
            print >> sys.stderr, """Show-Deferred::%s is mandatory.
  set via config file or command-line option %s"""%(i,j)

    Options = Cnf.subtree("Show-Deferred::Options")
    if Options["help"]:
        usage()

    # Initialise database connection
    DBConn()

    return args

def main():
    args = init()
    if len(args)!=0:
        usage(1)

    if Cnf.has_key("Show-Deferred::Options::Rrd"):
        rrd_dir = Cnf["Show-Deferred::Options::Rrd"]
    elif Cnf.has_key("Dir::Rrd"):
        rrd_dir = Cnf["Dir::Rrd"]
    else:
        rrd_dir = None

    filelist = []
    for r,d,f  in os.walk(Cnf["Show-Deferred::DeferredQueue"]):
        filelist += map (lambda x: os.path.join(r,x),
                         filter(lambda x: x.endswith('.changes'), f))
    list_uploads(filelist, rrd_dir)

    available_changes = set(map(os.path.basename,filelist))
    if Cnf.has_key("Show-Deferred::LinkPath"):
        # remove dead links
        for r,d,f in os.walk(Cnf["Show-Deferred::LinkPath"]):
            for af in f:
                afp = os.path.join(r,af)
                if (not os.path.exists(afp) or
                    (af.endswith('.changes') and af not in available_changes)):
                    os.unlink(afp)

if __name__ == '__main__':
    main()
