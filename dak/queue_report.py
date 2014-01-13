#!/usr/bin/env python

""" Produces a report on NEW and BYHAND packages """
# Copyright (C) 2001, 2002, 2003, 2005, 2006  James Troup <james@nocrew.org>

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

# <o-o> XP runs GCC, XFREE86, SSH etc etc,.,, I feel almost like linux....
# <o-o> I am very confident that I can replicate any Linux application on XP
# <willy> o-o: *boggle*
# <o-o> building from source.
# <o-o> Viiru: I already run GIMP under XP
# <willy> o-o: why do you capitalise the names of all pieces of software?
# <o-o> willy: because I want the EMPHASIZE them....
# <o-o> grr s/the/to/
# <willy> o-o: it makes you look like ZIPPY the PINHEAD
# <o-o> willy: no idea what you are talking about.
# <willy> o-o: do some research
# <o-o> willy: for what reason?

################################################################################

from copy import copy
import glob, os, stat, sys, time
import apt_pkg
try:
    import rrdtool
except ImportError:
    pass

from daklib import utils
from daklib.dbconn import DBConn, DBSource, has_new_comment, PolicyQueue, \
                          get_uid_from_fingerprint
from daklib.policy import PolicyQueueUploadHandler
from daklib.textutils import fix_maintainer
from daklib.utils import get_logins_from_ldap
from daklib.dak_exceptions import *

Cnf = None
direction = []
row_number = 0

################################################################################

def usage(exit_code=0):
    print """Usage: dak queue-report
Prints a report of packages in queues (usually new and byhand).

  -h, --help                show this help and exit.
  -8, --822                 writes 822 formated output to the location set in dak.conf
  -n, --new                 produce html-output
  -s, --sort=key            sort output according to key, see below.
  -a, --age=key             if using sort by age, how should time be treated?
                            If not given a default of hours will be used.
  -r, --rrd=key             Directory where rrd files to be updated are stored
  -d, --directories=key     A comma seperated list of queues to be scanned

     Sorting Keys: ao=age,   oldest first.   an=age,   newest first.
                   na=name,  ascending       nd=name,  descending
                   nf=notes, first           nl=notes, last

     Age Keys: m=minutes, h=hours, d=days, w=weeks, o=months, y=years

"""
    sys.exit(exit_code)

################################################################################

def plural(x):
    if x > 1:
        return "s"
    else:
        return ""

################################################################################

def time_pp(x):
    if x < 60:
        unit="second"
    elif x < 3600:
        x /= 60
        unit="minute"
    elif x < 86400:
        x /= 3600
        unit="hour"
    elif x < 604800:
        x /= 86400
        unit="day"
    elif x < 2419200:
        x /= 604800
        unit="week"
    elif x < 29030400:
        x /= 2419200
        unit="month"
    else:
        x /= 29030400
        unit="year"
    x = int(x)
    return "%s %s%s" % (x, unit, plural(x))

################################################################################

def sg_compare (a, b):
    a = a[1]
    b = b[1]
    """Sort by have pending action, have note, time of oldest upload."""
    # Sort by have pending action
    a_note_state = a["processed"]
    b_note_state = b["processed"]
    if a_note_state < b_note_state:
        return -1
    elif a_note_state > b_note_state:
        return 1

    # Sort by have note
    a_note_state = a["note_state"]
    b_note_state = b["note_state"]
    if a_note_state < b_note_state:
        return -1
    elif a_note_state > b_note_state:
        return 1

    # Sort by time of oldest upload
    return cmp(a["oldest"], b["oldest"])

############################################################

def sortfunc(a,b):
    for sorting in direction:
        (sortkey, way, time) = sorting
        ret = 0
        if time == "m":
            x=int(a[sortkey]/60)
            y=int(b[sortkey]/60)
        elif time == "h":
            x=int(a[sortkey]/3600)
            y=int(b[sortkey]/3600)
        elif time == "d":
            x=int(a[sortkey]/86400)
            y=int(b[sortkey]/86400)
        elif time == "w":
            x=int(a[sortkey]/604800)
            y=int(b[sortkey]/604800)
        elif time == "o":
            x=int(a[sortkey]/2419200)
            y=int(b[sortkey]/2419200)
        elif time == "y":
            x=int(a[sortkey]/29030400)
            y=int(b[sortkey]/29030400)
        else:
            x=a[sortkey]
            y=b[sortkey]
        if x < y:
            ret = -1
        elif x > y:
            ret = 1
        if ret != 0:
            if way < 0:
                ret = ret*-1
            return ret
    return 0

############################################################

def header():
    print """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="de" lang="de">
  <head>
    <meta http-equiv="content-type" content="text/xhtml+xml; charset=utf-8" />
    <link type="text/css" rel="stylesheet" href="style.css" />
    <link rel="shortcut icon" href="https://www.debian.org/favicon.ico" />
    <title>
      Debian NEW and BYHAND Packages
    </title>
    <script type="text/javascript">
    //<![CDATA[
    function togglePkg() {
        var children = document.getElementsByTagName("*");
        for (var i = 0; i < children.length; i++) {
            if(!children[i].hasAttribute("class"))
                continue;
            c = children[i].getAttribute("class").split(" ");
            for(var j = 0; j < c.length; j++) {
                if(c[j] == "sourceNEW") {
                    if (children[i].style.display == '')
                        children[i].style.display = 'none';
                    else children[i].style.display = '';
                }
            }
        }
    }
    //]]>
    </script>
  </head>
  <body id="NEW">
    <div id="logo">
      <a href="https://www.debian.org/">
        <img src="https://www.debian.org/logos/openlogo-nd-50.png"
        alt="debian logo" /></a>
      <a href="https://www.debian.org/">
        <img src="https://www.debian.org/Pics/debian.png"
        alt="Debian Project" /></a>
    </div>
    <div id="titleblock">

      <img src="https://www.debian.org/Pics/red-upperleft.png"
      id="red-upperleft" alt="corner image"/>
      <img src="https://www.debian.org/Pics/red-lowerleft.png"
      id="red-lowerleft" alt="corner image"/>
      <img src="https://www.debian.org/Pics/red-upperright.png"
      id="red-upperright" alt="corner image"/>
      <img src="https://www.debian.org/Pics/red-lowerright.png"
      id="red-lowerright" alt="corner image"/>
      <span class="title">
        Debian NEW and BYHAND Packages
      </span>
    </div>
    """

def footer():
    print "<p class=\"timestamp\">Timestamp: %s (UTC)</p>" % (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    print "<p class=\"timestamp\">There are <a href=\"/stat.html\">graphs about the queues</a> available.</p>"

    print """
    <div class="footer">
    <p>Hint: Age is the youngest upload of the package, if there is more than
    one version.<br />
    You may want to look at <a href="https://ftp-master.debian.org/REJECT-FAQ.html">the REJECT-FAQ</a>
      for possible reasons why one of the above packages may get rejected.</p>
    </div> </body> </html>
    """

def table_header(type, source_count, total_count):
    print "<h1 class='sourceNEW'>Summary for: %s</h1>" % (type)
    print "<h1 class='sourceNEW' style='display: none'>Summary for: binary-%s only</h1>" % (type)
    print """
    <p class="togglepkg" onclick="togglePkg()">Click to toggle all/binary-NEW packages</p>
    <table class="NEW">
      <caption class="sourceNEW">
    """
    print "Package count in <strong>%s</strong>: <em>%s</em>&nbsp;|&nbsp; Total Package count: <em>%s</em>" % (type, source_count, total_count)
    print """
      </caption>
      <thead>
        <tr>
          <th>Package</th>
          <th>Version</th>
          <th>Arch</th>
          <th>Distribution</th>
          <th>Age</th>
          <th>Upload info</th>
          <th>Closes</th>
        </tr>
      </thead>
      <tbody>
    """

def table_footer(type):
    print "</tbody></table>"


def table_row(source, version, arch, last_mod, maint, distribution, closes, fingerprint, sponsor, changedby):

    global row_number

    trclass = "sid"
    session = DBConn().session()
    for dist in distribution:
        if dist == "experimental":
            trclass = "exp"

    query = '''SELECT source
               FROM source_suite
               WHERE source = :source
               AND suite_name IN ('unstable', 'experimental')'''
    if not session.execute(query, {'source': source}).rowcount:
        trclass += " sourceNEW"
    session.commit()

    if row_number % 2 != 0:
        print "<tr class=\"%s even\">" % (trclass)
    else:
        print "<tr class=\"%s odd\">" % (trclass)

    if "sourceNEW" in trclass:
        print "<td class=\"package\">%s</td>" % (source)
    else:
        print "<td class=\"package\"><a href=\"http://packages.qa.debian.org/%(source)s\">%(source)s</a></td>" % {'source': source}
    print "<td class=\"version\">"
    for vers in version.split():
        print "<a href=\"new/%s_%s.html\">%s</a><br/>" % (source, utils.html_escape(vers), utils.html_escape(vers))
    print "</td>"
    print "<td class=\"arch\">%s</td>" % (arch)
    print "<td class=\"distribution\">"
    for dist in distribution:
        print "%s<br/>" % (dist)
    print "</td>"
    print "<td class=\"age\">%s</td>" % (last_mod)
    (name, mail) = maint.split(":", 1)

    print "<td class=\"upload-data\">"
    print "<span class=\"maintainer\">Maintainer: <a href=\"http://qa.debian.org/developer.php?login=%s\">%s</a></span><br/>" % (utils.html_escape(mail), utils.html_escape(name))
    (name, mail) = changedby.split(":", 1)
    print "<span class=\"changed-by\">Changed-By: <a href=\"http://qa.debian.org/developer.php?login=%s\">%s</a></span><br/>" % (utils.html_escape(mail), utils.html_escape(name))

    if sponsor:
        print "<span class=\"sponsor\">Sponsor: <a href=\"http://qa.debian.org/developer.php?login=%s\">%s</a>@debian.org</span><br/>" % (utils.html_escape(sponsor), utils.html_escape(sponsor))

    print "<span class=\"signature\">Fingerprint: %s</span>" % (fingerprint)
    print "</td>"

    print "<td class=\"closes\">"
    for close in closes:
        print "<a href=\"https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=%s\">#%s</a><br/>" % (utils.html_escape(close), utils.html_escape(close))
    print "</td></tr>"
    row_number+=1

############################################################

def update_graph_database(rrd_dir, type, n_source, n_binary):
    if not rrd_dir:
        return

    rrd_file = os.path.join(rrd_dir, type.lower()+'.rrd')
    update = [rrd_file, "N:%s:%s" % (n_source, n_binary)]

    try:
        rrdtool.update(*update)
    except rrdtool.error:
        create = [rrd_file]+"""
--step
300
--start
0
DS:ds0:GAUGE:7200:0:1000
DS:ds1:GAUGE:7200:0:1000
RRA:AVERAGE:0.5:1:599
RRA:AVERAGE:0.5:6:700
RRA:AVERAGE:0.5:24:775
RRA:AVERAGE:0.5:288:795
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

############################################################

def process_queue(queue, log, rrd_dir):
    msg = ""
    type = queue.queue_name
    session = DBConn().session()

    # Divide the .changes into per-source groups
    per_source = {}
    total_pending = 0
    for upload in queue.uploads:
        source = upload.changes.source
        if source not in per_source:
            per_source[source] = {}
            per_source[source]["list"] = []
            per_source[source]["processed"] = ""
            handler = PolicyQueueUploadHandler(upload, session)
            if handler.get_action():
                per_source[source]["processed"] = "PENDING %s" % handler.get_action()
                total_pending += 1
        per_source[source]["list"].append(upload)
        per_source[source]["list"].sort(lambda x, y: cmp(x.changes.created, y.changes.created), reverse=True)
    # Determine oldest time and have note status for each source group
    for source in per_source.keys():
        source_list = per_source[source]["list"]
        first = source_list[0]
        oldest = time.mktime(first.changes.created.timetuple())
        have_note = 0
        for d in per_source[source]["list"]:
            mtime = time.mktime(d.changes.created.timetuple())
            if Cnf.has_key("Queue-Report::Options::New"):
                if mtime > oldest:
                    oldest = mtime
            else:
                if mtime < oldest:
                    oldest = mtime
            have_note += has_new_comment(d.policy_queue, d.changes.source, d.changes.version)
        per_source[source]["oldest"] = oldest
        if not have_note:
            per_source[source]["note_state"] = 0; # none
        elif have_note < len(source_list):
            per_source[source]["note_state"] = 1; # some
        else:
            per_source[source]["note_state"] = 2; # all
    per_source_items = per_source.items()
    per_source_items.sort(sg_compare)

    update_graph_database(rrd_dir, type, len(per_source_items), len(queue.uploads))

    entries = []
    max_source_len = 0
    max_version_len = 0
    max_arch_len = 0
    try:
        logins = get_logins_from_ldap()
    except:
        logins = dict()
    for i in per_source_items:
        maintainer = {}
        maint=""
        distribution=""
        closes=""
        fingerprint=""
        changeby = {}
        changedby=""
        sponsor=""
        filename=i[1]["list"][0].changes.changesname
        last_modified = time.time()-i[1]["oldest"]
        source = i[1]["list"][0].changes.source
        if len(source) > max_source_len:
            max_source_len = len(source)
        binary_list = i[1]["list"][0].binaries
        binary = ', '.join([ b.package for b in binary_list ])
        arches = set()
        versions = set()
        for j in i[1]["list"]:
            dbc = j.changes
            changesbase = dbc.changesname

            if Cnf.has_key("Queue-Report::Options::New") or Cnf.has_key("Queue-Report::Options::822"):
                try:
                    (maintainer["maintainer822"], maintainer["maintainer2047"],
                    maintainer["maintainername"], maintainer["maintaineremail"]) = \
                    fix_maintainer (dbc.maintainer)
                except ParseMaintError as msg:
                    print "Problems while parsing maintainer address\n"
                    maintainer["maintainername"] = "Unknown"
                    maintainer["maintaineremail"] = "Unknown"
                maint="%s:%s" % (maintainer["maintainername"], maintainer["maintaineremail"])
                # ...likewise for the Changed-By: field if it exists.
                try:
                    (changeby["changedby822"], changeby["changedby2047"],
                     changeby["changedbyname"], changeby["changedbyemail"]) = \
                     fix_maintainer (dbc.changedby)
                except ParseMaintError as msg:
                    (changeby["changedby822"], changeby["changedby2047"],
                     changeby["changedbyname"], changeby["changedbyemail"]) = \
                     ("", "", "", "")
                changedby="%s:%s" % (changeby["changedbyname"], changeby["changedbyemail"])

                distribution=dbc.distribution.split()
                closes=dbc.closes

                fingerprint = dbc.fingerprint
                sponsor_name = get_uid_from_fingerprint(fingerprint).name
                sponsor_login = get_uid_from_fingerprint(fingerprint).uid
                if '@' in sponsor_login:
                    if fingerprint in logins:
                        sponsor_login = logins[fingerprint]
                if (sponsor_name != maintainer["maintainername"] and
                  sponsor_name != changeby["changedbyname"] and
                  sponsor_login + '@debian.org' != maintainer["maintaineremail"] and
                  sponsor_name != changeby["changedbyemail"]):
                    sponsor = sponsor_login

            for arch in dbc.architecture.split():
                arches.add(arch)
            versions.add(dbc.version)
        arches_list = list(arches)
        arches_list.sort(utils.arch_compare_sw)
        arch_list = " ".join(arches_list)
        version_list = " ".join(sorted(versions, reverse=True))
        if len(version_list) > max_version_len:
            max_version_len = len(version_list)
        if len(arch_list) > max_arch_len:
            max_arch_len = len(arch_list)
        if i[1]["note_state"]:
            note = " | [N]"
        else:
            note = ""
        entries.append([source, binary, version_list, arch_list, per_source[source]["processed"], note, last_modified, maint, distribution, closes, fingerprint, sponsor, changedby, filename])

    # direction entry consists of "Which field, which direction, time-consider" where
    # time-consider says how we should treat last_modified. Thats all.

    # Look for the options for sort and then do the sort.
    age = "h"
    if Cnf.has_key("Queue-Report::Options::Age"):
        age =  Cnf["Queue-Report::Options::Age"]
    if Cnf.has_key("Queue-Report::Options::New"):
    # If we produce html we always have oldest first.
        direction.append([6,-1,"ao"])
    else:
        if Cnf.has_key("Queue-Report::Options::Sort"):
            for i in Cnf["Queue-Report::Options::Sort"].split(","):
                if i == "ao":
                    # Age, oldest first.
                    direction.append([6,-1,age])
                elif i == "an":
                    # Age, newest first.
                    direction.append([6,1,age])
                elif i == "na":
                    # Name, Ascending.
                    direction.append([0,1,0])
                elif i == "nd":
                    # Name, Descending.
                    direction.append([0,-1,0])
                elif i == "nl":
                    # Notes last.
                    direction.append([5,1,0])
                elif i == "nf":
                    # Notes first.
                    direction.append([5,-1,0])
    entries.sort(lambda x, y: sortfunc(x, y))
    # Yes, in theory you can add several sort options at the commandline with. But my mind is to small
    # at the moment to come up with a real good sorting function that considers all the sidesteps you
    # have with it. (If you combine options it will simply take the last one at the moment).
    # Will be enhanced in the future.

    if Cnf.has_key("Queue-Report::Options::822"):
        # print stuff out in 822 format
        for entry in entries:
            (source, binary, version_list, arch_list, processed, note, last_modified, maint, distribution, closes, fingerprint, sponsor, changedby, changes_file) = entry

            # We'll always have Source, Version, Arch, Mantainer, and Dist
            # For the rest, check to see if we have them, then print them out
            log.write("Source: " + source + "\n")
            log.write("Binary: " + binary + "\n")
            log.write("Version: " + version_list + "\n")
            log.write("Architectures: ")
            log.write( (", ".join(arch_list.split(" "))) + "\n")
            log.write("Age: " + time_pp(last_modified) + "\n")
            log.write("Last-Modified: " + str(int(time.time()) - int(last_modified)) + "\n")
            log.write("Queue: " + type + "\n")

            (name, mail) = maint.split(":", 1)
            log.write("Maintainer: " + name + " <"+mail+">" + "\n")
            if changedby:
               (name, mail) = changedby.split(":", 1)
               log.write("Changed-By: " + name + " <"+mail+">" + "\n")
            if sponsor:
               log.write("Sponsored-By: %s@debian.org\n" % sponsor)
            log.write("Distribution:")
            for dist in distribution:
               log.write(" " + dist)
            log.write("\n")
            log.write("Fingerprint: " + fingerprint + "\n")
            if closes:
                bug_string = ""
                for bugs in closes:
                    bug_string += "#"+bugs+", "
                log.write("Closes: " + bug_string[:-2] + "\n")
            log.write("Changes-File: " + os.path.basename(changes_file) + "\n")
            log.write("\n")

    total_count = len(queue.uploads)
    source_count = len(per_source_items)

    if Cnf.has_key("Queue-Report::Options::New"):
        direction.append([6,1,"ao"])
        entries.sort(lambda x, y: sortfunc(x, y))
    # Output for a html file. First table header. then table_footer.
    # Any line between them is then a <tr> printed from subroutine table_row.
        if len(entries) > 0:
            table_header(type.upper(), source_count, total_count)
            for entry in entries:
                (source, binary, version_list, arch_list, processed, note, last_modified, maint, distribution, closes, fingerprint, sponsor, changedby, undef) = entry
                table_row(source, version_list, arch_list, time_pp(last_modified), maint, distribution, closes, fingerprint, sponsor, changedby)
            table_footer(type.upper())
    elif not Cnf.has_key("Queue-Report::Options::822"):
    # The "normal" output without any formatting.
        msg = ""
        for entry in entries:
            (source, binary, version_list, arch_list, processed, note, last_modified, undef, undef, undef, undef, undef, undef, undef) = entry
            if processed:
                format="%%-%ds | %%-%ds | %%-%ds | %%s\n" % (max_source_len, max_version_len, max_arch_len)
                msg += format % (source, version_list, arch_list, processed)
            else:
                format="%%-%ds | %%-%ds | %%-%ds%%s | %%s old\n" % (max_source_len, max_version_len, max_arch_len)
                msg += format % (source, version_list, arch_list, note, time_pp(last_modified))

        if msg:
            print type.upper()
            print "-"*len(type)
            print
            print msg
            print ("%s %s source package%s / %s %s package%s in total / %s %s package%s to be processed." %
                   (source_count, type, plural(source_count),
                    total_count, type, plural(total_count),
                    total_pending, type, plural(total_pending)))
            print

################################################################################

def main():
    global Cnf

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Queue-Report::Options::Help"),
                 ('n',"new","Queue-Report::Options::New"),
                 ('8','822',"Queue-Report::Options::822"),
                 ('s',"sort","Queue-Report::Options::Sort", "HasArg"),
                 ('a',"age","Queue-Report::Options::Age", "HasArg"),
                 ('r',"rrd","Queue-Report::Options::Rrd", "HasArg"),
                 ('d',"directories","Queue-Report::Options::Directories", "HasArg")]
    for i in [ "help" ]:
        if not Cnf.has_key("Queue-Report::Options::%s" % (i)):
            Cnf["Queue-Report::Options::%s" % (i)] = ""

    apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)

    Options = Cnf.subtree("Queue-Report::Options")
    if Options["Help"]:
        usage()

    if Cnf.has_key("Queue-Report::Options::New"):
        header()

    queue_names = []

    if Cnf.has_key("Queue-Report::Options::Directories"):
        for i in Cnf["Queue-Report::Options::Directories"].split(","):
            queue_names.append(i)
    elif Cnf.has_key("Queue-Report::Directories"):
        queue_names = Cnf.value_list("Queue-Report::Directories")
    else:
        queue_names = [ "byhand", "new" ]

    if Cnf.has_key("Queue-Report::Options::Rrd"):
        rrd_dir = Cnf["Queue-Report::Options::Rrd"]
    elif Cnf.has_key("Dir::Rrd"):
        rrd_dir = Cnf["Dir::Rrd"]
    else:
        rrd_dir = None

    f = None
    if Cnf.has_key("Queue-Report::Options::822"):
        # Open the report file
        f = open(Cnf["Queue-Report::ReportLocations::822Location"], "w")

    session = DBConn().session()

    for queue_name in queue_names:
        queue = session.query(PolicyQueue).filter_by(queue_name=queue_name).first()
        if queue is not None:
            process_queue(queue, f, rrd_dir)
        else:
            utils.warn("Cannot find queue %s" % queue_name)

    if Cnf.has_key("Queue-Report::Options::822"):
        f.close()

    if Cnf.has_key("Queue-Report::Options::New"):
        footer()

################################################################################

if __name__ == '__main__':
    main()
