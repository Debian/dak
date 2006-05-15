#!/usr/bin/env python

# Produces a report on NEW and BYHAND packages
# Copyright (C) 2001, 2002, 2003, 2005  James Troup <james@nocrew.org>
# $Id: helena,v 1.6 2005-11-15 09:50:32 ajt Exp $

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

import copy, glob, os, stat, sys, time;
import apt_pkg;
import katie, utils;
import encodings.utf_8, encodings.latin_1, string;

Cnf = None;
Katie = None;
direction = [];
row_number = 0;

################################################################################

def usage(exit_code=0):
    print """Usage: helena
Prints a report of packages in queue directories (usually new and byhand).

  -h, --help                show this help and exit.
  -n, --new                 produce html-output
  -s, --sort=key            sort output according to key, see below.
  -a, --age=key             if using sort by age, how should time be treated?
                            If not given a default of hours will be used.

     Sorting Keys: ao=age,   oldest first.   an=age,   newest first.
                   na=name,  ascending       nd=name,  descending
                   nf=notes, first           nl=notes, last

     Age Keys: m=minutes, h=hours, d=days, w=weeks, o=months, y=years
     
"""
    sys.exit(exit_code)

################################################################################

def plural(x):
    if x > 1:
        return "s";
    else:
        return "";

################################################################################

def time_pp(x):
    if x < 60:
        unit="second";
    elif x < 3600:
        x /= 60;
        unit="minute";
    elif x < 86400:
        x /= 3600;
        unit="hour";
    elif x < 604800:
        x /= 86400;
        unit="day";
    elif x < 2419200:
        x /= 604800;
        unit="week";
    elif x < 29030400:
        x /= 2419200;
        unit="month";
    else:
        x /= 29030400;
        unit="year";
    x = int(x);
    return "%s %s%s" % (x, unit, plural(x));

################################################################################

def sg_compare (a, b):
    a = a[1];
    b = b[1];
    """Sort by have note, time of oldest upload."""
    # Sort by have note
    a_note_state = a["note_state"];
    b_note_state = b["note_state"];
    if a_note_state < b_note_state:
        return -1;
    elif a_note_state > b_note_state:
        return 1;

    # Sort by time of oldest upload
    return cmp(a["oldest"], b["oldest"]);

############################################################

def sortfunc(a,b):
     for sorting in direction:
         (sortkey, way, time) = sorting;
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
    print """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
	<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso8859-1">
	<title>Debian NEW and BYHAND Packages</title>
	<link type="text/css" rel="stylesheet" href="style.css">
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
     alt="" width="15" height="16"></td>
	<td rowspan="2" class="reddy">Debian NEW and BYHAND Packages</td>
	<td class="reddy">
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

def footer():
    print "<p class=\"validate\">Timestamp: %s (UTC)</p>" % (time.strftime("%d.%m.%Y / %H:%M:%S", time.gmtime()))
    print "<hr><p>Hint: Age is the youngest upload of the package, if there is more than one version.</p>"
    print "<p>You may want to look at <a href=\"http://ftp-master.debian.org/REJECT-FAQ.html\">the REJECT-FAQ</a> for possible reasons why one of the above packages may get rejected.</p>"
    print """<a href="http://validator.w3.org/check?uri=referer">
    <img border="0" src="http://www.w3.org/Icons/valid-html401" alt="Valid HTML 4.01!" height="31" width="88"></a>
	<a href="http://jigsaw.w3.org/css-validator/check/referer">
    <img border="0" src="http://jigsaw.w3.org/css-validator/images/vcss" alt="Valid CSS!"
     height="31" width="88"></a>
    """
    print "</body></html>"

def table_header(type):
    print "<h1>Summary for: %s</h1>" % (type)
    print """<center><table border="0">
	<tr>
	  <th align="center">Package</th>
	  <th align="center">Version</th>
	  <th align="center">Arch</th>
	  <th align="center">Distribution</th>
	  <th align="center">Age</th>
	  <th align="center">Maintainer</th>
	  <th align="center">Closes</th>
	</tr>
	"""

def table_footer(type, source_count, total_count):
    print "</table></center><br>\n"
    print "<p class=\"validate\">Package count in <b>%s</b>: <i>%s</i>\n" % (type, source_count)
    print "<br>Total Package count: <i>%s</i></p>\n" % (total_count)

def force_to_latin(s):
    """Forces a string to Latin-1."""
    latin1_s = unicode(s,'utf-8');
    return latin1_s.encode('iso8859-1', 'replace');


def table_row(source, version, arch, last_mod, maint, distribution, closes):

    global row_number;

    if row_number % 2 != 0:
        print "<tr class=\"even\">"
    else:
        print "<tr class=\"odd\">"

    tdclass = "sid"
    for dist in distribution:
        if dist == "experimental":
            tdclass = "exp";
    print "<td valign=\"top\" class=\"%s\">%s</td>" % (tdclass, source);
    print "<td valign=\"top\" class=\"%s\">" % (tdclass)
    for vers in version.split():
        print "%s<br>" % (vers);
    print "</td><td valign=\"top\" class=\"%s\">%s</td><td valign=\"top\" class=\"%s\">" % (tdclass, arch, tdclass);
    for dist in distribution:
        print "%s<br>" % (dist);
    print "</td><td valign=\"top\" class=\"%s\">%s</td>" % (tdclass, last_mod);
    (name, mail) = maint.split(":");
    name = force_to_latin(name);

    print "<td valign=\"top\" class=\"%s\"><a href=\"http://qa.debian.org/developer.php?login=%s\">%s</a></td>" % (tdclass, mail, name);
    print "<td valign=\"top\" class=\"%s\">" % (tdclass)
    for close in closes:
        print "<a href=\"http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=%s\">#%s</a><br>" % (close, close);
    print "</td></tr>";
    row_number+=1;
    
############################################################

def process_changes_files(changes_files, type):
    msg = "";
    cache = {};
    # Read in all the .changes files
    for filename in changes_files:
        try:
            Katie.pkg.changes_file = filename;
            Katie.init_vars();
            Katie.update_vars();
            cache[filename] = copy.copy(Katie.pkg.changes);
            cache[filename]["filename"] = filename;
        except:
            break;
    # Divide the .changes into per-source groups
    per_source = {};
    for filename in cache.keys():
        source = cache[filename]["source"];
        if not per_source.has_key(source):
            per_source[source] = {};
            per_source[source]["list"] = [];
        per_source[source]["list"].append(cache[filename]);
    # Determine oldest time and have note status for each source group
    for source in per_source.keys():
        source_list = per_source[source]["list"];
        first = source_list[0];
        oldest = os.stat(first["filename"])[stat.ST_MTIME];
        have_note = 0;
        for d in per_source[source]["list"]:
            mtime = os.stat(d["filename"])[stat.ST_MTIME];
            if Cnf.has_key("Helena::Options::New"):
                if mtime > oldest:
                    oldest = mtime;
            else:
                if mtime < oldest:
                    oldest = mtime;
            have_note += (d.has_key("lisa note"));
        per_source[source]["oldest"] = oldest;
        if not have_note:
            per_source[source]["note_state"] = 0; # none
        elif have_note < len(source_list):
            per_source[source]["note_state"] = 1; # some
        else:
            per_source[source]["note_state"] = 2; # all
    per_source_items = per_source.items();
    per_source_items.sort(sg_compare);

    entries = [];
    max_source_len = 0;
    max_version_len = 0;
    max_arch_len = 0;
    maintainer = {};
    maint="";
    distribution="";
    closes="";
    source_exists="";
    for i in per_source_items:
        last_modified = time.time()-i[1]["oldest"];
        source = i[1]["list"][0]["source"];
        if len(source) > max_source_len:
            max_source_len = len(source);
        arches = {};
        versions = {};
        for j in i[1]["list"]:
            if Cnf.has_key("Helena::Options::New"):
                try:
                    (maintainer["maintainer822"], maintainer["maintainer2047"],
                    maintainer["maintainername"], maintainer["maintaineremail"]) = \
                    utils.fix_maintainer (j["maintainer"]);
                except utils.ParseMaintError, msg:
                    print "Problems while parsing maintainer address\n";
                    maintainer["maintainername"] = "Unknown";
                    maintainer["maintaineremail"] = "Unknown";
                maint="%s:%s" % (maintainer["maintainername"], maintainer["maintaineremail"]);
                distribution=j["distribution"].keys();
                closes=j["closes"].keys();
            for arch in j["architecture"].keys():
                arches[arch] = "";
            version = j["version"];
            versions[version] = "";
        arches_list = arches.keys();
        arches_list.sort(utils.arch_compare_sw);
        arch_list = " ".join(arches_list);
        version_list = " ".join(versions.keys());
        if len(version_list) > max_version_len:
            max_version_len = len(version_list);
        if len(arch_list) > max_arch_len:
            max_arch_len = len(arch_list);
        if i[1]["note_state"]:
            note = " | [N]";
        else:
            note = "";
        entries.append([source, version_list, arch_list, note, last_modified, maint, distribution, closes]);

    # direction entry consists of "Which field, which direction, time-consider" where
    # time-consider says how we should treat last_modified. Thats all.

    # Look for the options for sort and then do the sort.
    age = "h"
    if Cnf.has_key("Helena::Options::Age"):
        age =  Cnf["Helena::Options::Age"]
    if Cnf.has_key("Helena::Options::New"):
    # If we produce html we always have oldest first.
        direction.append([4,-1,"ao"]);
    else:
		if Cnf.has_key("Helena::Options::Sort"):
			for i in Cnf["Helena::Options::Sort"].split(","):
			  if i == "ao":
				  # Age, oldest first.
				  direction.append([4,-1,age]);
			  elif i == "an":
				  # Age, newest first.
				  direction.append([4,1,age]);
			  elif i == "na":
				  # Name, Ascending.
				  direction.append([0,1,0]);
			  elif i == "nd":
				  # Name, Descending.
				  direction.append([0,-1,0]);
			  elif i == "nl":
				  # Notes last.
				  direction.append([3,1,0]);
			  elif i == "nf":
				  # Notes first.
				  direction.append([3,-1,0]);
    entries.sort(lambda x, y: sortfunc(x, y))
    # Yes, in theory you can add several sort options at the commandline with. But my mind is to small
    # at the moment to come up with a real good sorting function that considers all the sidesteps you
    # have with it. (If you combine options it will simply take the last one at the moment).
    # Will be enhanced in the future.

    if Cnf.has_key("Helena::Options::New"):
        direction.append([4,1,"ao"]);
        entries.sort(lambda x, y: sortfunc(x, y))
    # Output for a html file. First table header. then table_footer.
    # Any line between them is then a <tr> printed from subroutine table_row.
        if len(entries) > 0:
            table_header(type.upper());
            for entry in entries:
                (source, version_list, arch_list, note, last_modified, maint, distribution, closes) = entry;
                table_row(source, version_list, arch_list, time_pp(last_modified), maint, distribution, closes);
            total_count = len(changes_files);
            source_count = len(per_source_items);
            table_footer(type.upper(), source_count, total_count);
    else:
    # The "normal" output without any formatting.
        format="%%-%ds | %%-%ds | %%-%ds%%s | %%s old\n" % (max_source_len, max_version_len, max_arch_len)

        msg = "";
        for entry in entries:
            (source, version_list, arch_list, note, last_modified, undef, undef, undef) = entry;
            msg += format % (source, version_list, arch_list, note, time_pp(last_modified));

        if msg:
            total_count = len(changes_files);
            source_count = len(per_source_items);
            print type.upper();
            print "-"*len(type);
            print
            print msg;
            print "%s %s source package%s / %s %s package%s in total." % (source_count, type, plural(source_count), total_count, type, plural(total_count));
            print


################################################################################

def main():
    global Cnf, Katie;

    Cnf = utils.get_conf();
    Arguments = [('h',"help","Helena::Options::Help"),
				 ('n',"new","Helena::Options::New"),
                 ('s',"sort","Helena::Options::Sort", "HasArg"),
                 ('a',"age","Helena::Options::Age", "HasArg")];
    for i in [ "help" ]:
	if not Cnf.has_key("Helena::Options::%s" % (i)):
	    Cnf["Helena::Options::%s" % (i)] = "";

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv);

    Options = Cnf.SubTree("Helena::Options")
    if Options["Help"]:
	usage();

    Katie = katie.Katie(Cnf);

    if Cnf.has_key("Helena::Options::New"):
        header();

    directories = Cnf.ValueList("Helena::Directories");
    if not directories:
        directories = [ "byhand", "new" ];

    for directory in directories:
        changes_files = glob.glob("%s/*.changes" % (Cnf["Dir::Queue::%s" % (directory)]));
        process_changes_files(changes_files, directory);

    if Cnf.has_key("Helena::Options::New"):
        footer();

################################################################################

if __name__ == '__main__':
    main();
