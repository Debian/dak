#!/usr/bin/env python

# Script to automate some parts of checking NEW packages
# Copyright (C) 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>

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

# <Omnic> elmo wrote docs?!!?!?!?!?!?!
# <aj> as if he wasn't scary enough before!!
# * aj imagines a little red furry toy sitting hunched over a computer
#   tapping furiously and giggling to himself
# <aj> eventually he stops, and his heads slowly spins around and you
#      see this really evil grin and then he sees you, and picks up a
#      knife from beside the keyboard and throws it at you, and as you
#      breathe your last breath, he starts giggling again
# <aj> but i should be telling this to my psychiatrist, not you guys,
#      right? :)

################################################################################

import errno, os, pg, re, sys, md5
import apt_pkg, apt_inst
import daklib.database, daklib.utils, daklib.queue

################################################################################

re_package = re.compile(r"^(.+?)_.*")
re_doc_directory = re.compile(r".*/doc/([^/]*).*")

re_contrib = re.compile('^contrib/')
re_nonfree = re.compile('^non\-free/')

re_arch = re.compile("Architecture: .*")
re_builddep = re.compile("Build-Depends: .*")
re_builddepind = re.compile("Build-Depends-Indep: .*")

re_localhost = re.compile("localhost\.localdomain")
re_version = re.compile('^(.*)\((.*)\)')

re_newlinespace = re.compile('\n')
re_spacestrip = re.compile('(\s)')

html_escaping = {'"':'&quot;', '&':'&amp;', '<':'&lt;', '>':'&gt;'}
re_html_escaping = re.compile('|'.join(map(re.escape, html_escaping.keys())))

################################################################################

Cnf = None
projectB = None

Cnf = daklib.utils.get_conf()
projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
daklib.database.init(Cnf, projectB)

printed_copyrights = {}

# default is to not output html.
use_html = 0

################################################################################

def usage (exit_code=0):
    print """Usage: dak examine-package [PACKAGE]...
Check NEW package(s).

  -h, --help                 show this help and exit
  -H, --html-output          output html page with inspection result
  -f, --file-name            filename for the html page

PACKAGE can be a .changes, .dsc, .deb or .udeb filename."""

    sys.exit(exit_code)

################################################################################
# probably xml.sax.saxutils would work as well

def html_escape(s):
  return re_html_escaping.sub(lambda x: html_escaping.get(x.group(0)), s)

def escape_if_needed(s):
  if use_html:
    return re_html_escaping.sub(html_escaping.get, s)
  else:
    return s
  
def headline(s, level=2):
  if use_html:
    print "<h%d>%s</h%d>" % (level, html_escape(s), level)
  else:
    print "---- %s ----" % (s)

# Colour definitions, 'end' isn't really for use

ansi_colours = {
  'main': "\033[36m",
  'contrib': "\033[33m",
  'nonfree': "\033[31m",
  'arch': "\033[32m",
  'end': "\033[0m",
  'bold': "\033[1m",
  'maintainer': "\033[32m"}

html_colours = {
  'main': ('<span style="color: aqua">',"</span>"),
  'contrib': ('<span style="color: yellow">',"</span>"),
  'nonfree': ('<span style="color: red">',"</span>"),
  'arch': ('<span style="color: green">',"</span>"),
  'bold': ('<span style="font-weight: bold">',"</span>"),
  'maintainer': ('<span style="color: green">',"</span>")}

def colour_output(s, colour):
  if use_html:
    return ("%s%s%s" % (html_colours[colour][0], html_escape(s), html_colours[colour][1]))
  else:
    return ("%s%s%s" % (ansi_colours[colour], s, ansi_colours['end']))

def print_escaped_text(s):
  if use_html:
    print "<pre>%s</pre>" % (s)
  else:
    print s  

def print_formatted_text(s):
  if use_html:
    print "<pre>%s</pre>" % (html_escape(s))
  else:
    print s

################################################################################

def get_depends_parts(depend) :
    v_match = re_version.match(depend)
    if v_match:
	d_parts = { 'name' : v_match.group(1), 'version' : v_match.group(2) }
    else :
	d_parts = { 'name' : depend , 'version' : '' }
    return d_parts

def get_or_list(depend) :
    or_list = depend.split("|")
    return or_list

def get_comma_list(depend) :
    dep_list = depend.split(",")
    return dep_list

def split_depends (d_str) :
    # creates a list of lists of dictionaries of depends (package,version relation)

    d_str = re_spacestrip.sub('',d_str)
    depends_tree = []
    # first split depends string up amongs comma delimiter
    dep_list = get_comma_list(d_str)
    d = 0
    while d < len(dep_list):
	# put depends into their own list
	depends_tree.append([dep_list[d]])
	d += 1
    d = 0
    while d < len(depends_tree):
	k = 0
	# split up Or'd depends into a multi-item list
	depends_tree[d] = get_or_list(depends_tree[d][0])
	while k < len(depends_tree[d]):
	    # split depends into {package, version relation}
	    depends_tree[d][k] = get_depends_parts(depends_tree[d][k])
	    k += 1
	d += 1
    return depends_tree

def read_control (filename):
    recommends = []
    depends = []
    section = ''
    maintainer = ''
    arch = ''

    deb_file = daklib.utils.open_file(filename)
    try:
	extracts = apt_inst.debExtractControl(deb_file)
	control = apt_pkg.ParseSection(extracts)
    except:
	print_formatted_text("can't parse control info")
	# TV-COMMENT: this will raise exceptions in two lines
	control = ''

    deb_file.close()

    control_keys = control.keys()

    if control.has_key("Depends"):
	depends_str = control.Find("Depends")
	# create list of dependancy lists
	depends = split_depends(depends_str)

    if control.has_key("Recommends"):
	recommends_str = control.Find("Recommends")
	recommends = split_depends(recommends_str)

    if control.has_key("Section"):
	section_str = control.Find("Section")

	c_match = re_contrib.search(section_str)
	nf_match = re_nonfree.search(section_str)
	if c_match :
	    # contrib colour
	    section = colour_output(section_str, 'contrib')
	elif nf_match :
	    # non-free colour
	    section = colour_output(section_str, 'nonfree')
	else :
	    # main
	    section = colour_output(section_str, 'main')
    if control.has_key("Architecture"):
	arch_str = control.Find("Architecture")
   	arch = colour_output(arch_str, 'arch')

    if control.has_key("Maintainer"):
	maintainer = control.Find("Maintainer")
   	localhost = re_localhost.search(maintainer)
	if localhost:
	    #highlight bad email
	    maintainer = colour_output(maintainer, 'maintainer')
	else:
	    maintainer = escape_if_needed(maintainer)

    return (control, control_keys, section, depends, recommends, arch, maintainer)

def read_dsc (dsc_filename):
    dsc = {}

    dsc_file = daklib.utils.open_file(dsc_filename)
    try:
	dsc = daklib.utils.parse_changes(dsc_filename)
    except:
	print_formatted_text("can't parse control info")
    dsc_file.close()

    filecontents = escape_if_needed(strip_pgp_signature(dsc_filename))

    if dsc.has_key("build-depends"):
	builddep = split_depends(dsc["build-depends"])
	builddepstr = create_depends_string(builddep)
	filecontents = re_builddep.sub("Build-Depends: "+builddepstr, filecontents)

    if dsc.has_key("build-depends-indep"):
	builddepindstr = create_depends_string(split_depends(dsc["build-depends-indep"]))
	filecontents = re_builddepind.sub("Build-Depends-Indep: "+builddepindstr, filecontents)

    if dsc.has_key("architecture") :
	if (dsc["architecture"] != "any"):
	    newarch = colour_output(dsc["architecture"], 'arch')
	    filecontents = re_arch.sub("Architecture: " + newarch, filecontents)

    return filecontents

def create_depends_string (depends_tree):
    # just look up unstable for now. possibly pull from .changes later
    suite = "unstable"
    result = ""
    comma_count = 1
    for l in depends_tree:
	if (comma_count >= 2):
	    result += ", "
	or_count = 1
	for d in l:
	    if (or_count >= 2 ):
		result += " | "
	    # doesn't do version lookup yet.

	    q = projectB.query("SELECT DISTINCT(b.package), b.version, c.name, su.suite_name FROM  binaries b, files fi, location l, component c, bin_associations ba, suite su WHERE b.package='%s' AND b.file = fi.id AND fi.location = l.id AND l.component = c.id AND ba.bin=b.id AND ba.suite = su.id AND su.suite_name='%s' ORDER BY b.version desc" % (d['name'], suite))
	    ql = q.getresult()
	    if ql:
		i = ql[0]

		adepends = d['name']
		if d['version'] != '' :
		    adepends += " (%s)" % (d['version'])
		
		if i[2] == "contrib":
		    result += colour_output(adepends, "contrib")
		elif i[2] == "non-free":
		    result += colour_output(adepends, "nonfree")
		else :
		    result += colour_output(adepends, "main")
	    else:
		adepends = d['name']
		if d['version'] != '' :
		    adepends += " (%s)" % (d['version'])
		result += colour_output(adepends, "bold")
	    or_count += 1
	comma_count += 1
    return result

def output_deb_info(filename):
    (control, control_keys, section, depends, recommends, arch, maintainer) = read_control(filename)

    to_print = ""
    if control == '':
	print_formatted_text("no control info")
    else:
	for key in control_keys :
	    output = " " + key + ": "
	    if key == 'Depends':
		output += create_depends_string(depends)
	    elif key == 'Recommends':
		output += create_depends_string(recommends)
	    elif key == 'Section':
		output += section
	    elif key == 'Architecture':
		output += arch
	    elif key == 'Maintainer':
		output += maintainer
	    elif key == 'Description':
		desc = control.Find(key)
		desc = re_newlinespace.sub('\n ', desc)
		output += escape_if_needed(desc)
	    else:
		output += escape_if_needed(control.Find(key))
            to_print += output + '\n'
        print_escaped_text(to_print)

def do_command (command, filename):
    o = os.popen("%s %s" % (command, filename))
    print_formatted_text(o.read())

def do_lintian (filename):
    # lintian currently does not have html coloring, so dont use color for lintian (yet)
    if use_html:
        do_command("lintian --show-overrides", filename)
    else:
        do_command("lintian --show-overrides --color always", filename)

def print_copyright (deb_filename):
    package = re_package.sub(r'\1', deb_filename)
    o = os.popen("dpkg-deb -c %s | egrep 'usr(/share)?/doc/[^/]*/copyright' | awk '{print $6}' | head -n 1" % (deb_filename))
    copyright = o.read()[:-1]

    if copyright == "":
        print_formatted_text("WARNING: No copyright found, please check package manually.")
        return

    doc_directory = re_doc_directory.sub(r'\1', copyright)
    if package != doc_directory:
        print_formatted_text("WARNING: wrong doc directory (expected %s, got %s)." % (package, doc_directory))
        return

    o = os.popen("dpkg-deb --fsys-tarfile %s | tar xvOf - %s 2>/dev/null" % (deb_filename, copyright))
    copyright = o.read()
    copyrightmd5 = md5.md5(copyright).hexdigest()

    if printed_copyrights.has_key(copyrightmd5) and printed_copyrights[copyrightmd5] != "%s (%s)" % (package, deb_filename):
        print_formatted_text( "NOTE: Copyright is the same as %s.\n" % \
		(printed_copyrights[copyrightmd5]))
    else:
	printed_copyrights[copyrightmd5] = "%s (%s)" % (package, deb_filename)

    print_formatted_text(copyright)

def check_dsc (dsc_filename):
    headline(".dsc file for %s" % (dsc_filename))
    (dsc) = read_dsc(dsc_filename)
    print_escaped_text(dsc)
    headline("lintian check for %s" % (dsc_filename))
    do_lintian(dsc_filename)

def check_deb (deb_filename):
    filename = os.path.basename(deb_filename)

    if filename.endswith(".udeb"):
	is_a_udeb = 1
    else:
	is_a_udeb = 0

    headline("control file for %s" % (filename))
    #do_command ("dpkg -I", deb_filename)
    output_deb_info(deb_filename)

    if is_a_udeb:
	headline("skipping lintian check for udeb")
	print 
    else:
	headline("lintian check for %s" % (filename))
        do_lintian(deb_filename)

    headline("contents of %s" % (filename))
    do_command ("dpkg -c", deb_filename)

    if is_a_udeb:
	headline("skipping copyright for udeb")
    else:
	headline("copyright of %s" % (filename))
        print_copyright(deb_filename)

    headline("file listing of %s" % (filename))
    do_command ("ls -l", deb_filename)

# Read a file, strip the signature and return the modified contents as
# a string.
def strip_pgp_signature (filename):
    file = daklib.utils.open_file (filename)
    contents = ""
    inside_signature = 0
    skip_next = 0
    for line in file.readlines():
        if line[:-1] == "":
            continue
        if inside_signature:
            continue
        if skip_next:
            skip_next = 0
            continue
        if line.startswith("-----BEGIN PGP SIGNED MESSAGE"):
            skip_next = 1
            continue
        if line.startswith("-----BEGIN PGP SIGNATURE"):
            inside_signature = 1
            continue
        if line.startswith("-----END PGP SIGNATURE"):
            inside_signature = 0
            continue
	contents += line
    file.close()
    return contents

# Display the .changes [without the signature]
def display_changes (changes_filename):
    headline(".changes file for %s" % (changes_filename))
    print_formatted_text(strip_pgp_signature(changes_filename))

def check_changes (changes_filename):
    display_changes(changes_filename)

    changes = daklib.utils.parse_changes (changes_filename)
    files = daklib.utils.build_file_list(changes)
    for file in files.keys():
	if file.endswith(".deb") or file.endswith(".udeb"):
	    check_deb(file)
        if file.endswith(".dsc"):
            check_dsc(file)
        # else: => byhand

def main ():
    global Cnf, projectB, db_files, waste, excluded

#    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Examine-Package::Options::Help"),
                 ('H',"html-output","Examine-Package::Options::Html-Output"),
                ]
    for i in [ "Help", "Html-Output", "partial-html" ]:
	if not Cnf.has_key("Examine-Package::Options::%s" % (i)):
	    Cnf["Examine-Package::Options::%s" % (i)] = ""

    args = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Examine-Package::Options")

    if Options["Help"]:
	usage()

    stdout_fd = sys.stdout

    for file in args:
        try:
	    if not Options["Html-Output"]:
		# Pipe output for each argument through less
		less_fd = os.popen("less -R -", 'w', 0)
		# -R added to display raw control chars for colour
		sys.stdout = less_fd
            try:
                if file.endswith(".changes"):
                    check_changes(file)
                elif file.endswith(".deb") or file.endswith(".udeb"):
                    check_deb(file)
                elif file.endswith(".dsc"):
                    check_dsc(file)
                else:
                    daklib.utils.fubar("Unrecognised file type: '%s'." % (file))
            finally:
		if not Options["Html-Output"]:
		    # Reset stdout here so future less invocations aren't FUBAR
		    less_fd.close()
		    sys.stdout = stdout_fd
        except IOError, e:
            if errno.errorcode[e.errno] == 'EPIPE':
                daklib.utils.warn("[examine-package] Caught EPIPE; skipping.")
                pass
            else:
                raise
        except KeyboardInterrupt:
            daklib.utils.warn("[examine-package] Caught C-c; skipping.")
            pass

#######################################################################################

if __name__ == '__main__':
    main()

