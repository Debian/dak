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
import daklib.database, daklib.utils

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

################################################################################

# Colour definitions

# Main
main_colour = "\033[36m"
# Contrib
contrib_colour = "\033[33m"
# Non-Free
nonfree_colour = "\033[31m"
# Arch
arch_colour = "\033[32m"
# End
end_colour = "\033[0m"
# Bold
bold_colour = "\033[1m"
# Bad maintainer
maintainer_colour = arch_colour

################################################################################

Cnf = None
projectB = None

Cnf = daklib.utils.get_conf()
projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
daklib.database.init(Cnf, projectB)

printed_copyrights = {}

################################################################################

def usage (exit_code=0):
    print """Usage: dak examine-package [PACKAGE]...
Check NEW package(s).

  -h, --help                 show this help and exit

PACKAGE can be a .changes, .dsc, .deb or .udeb filename."""

    sys.exit(exit_code)

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
	print "can't parse control info"
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
	    section = contrib_colour + section_str + end_colour
	elif nf_match :
	    # non-free colour
	    section = nonfree_colour + section_str + end_colour
	else :
	    # main
	    section = main_colour +  section_str + end_colour
    if control.has_key("Architecture"):
	arch_str = control.Find("Architecture")
   	arch = arch_colour + arch_str + end_colour

    if control.has_key("Maintainer"):
	maintainer = control.Find("Maintainer")
   	localhost = re_localhost.search(maintainer)
	if localhost:
	    #highlight bad email
	    maintainer = maintainer_colour + maintainer + end_colour

    return (control, control_keys, section, depends, recommends, arch, maintainer)

def read_dsc (dsc_filename):
    dsc = {}

    dsc_file = daklib.utils.open_file(dsc_filename)
    try:
	dsc = daklib.utils.parse_changes(dsc_filename)
    except:
	print "can't parse control info"
    dsc_file.close()

    filecontents = strip_pgp_signature(dsc_filename)

    if dsc.has_key("build-depends"):
	builddep = split_depends(dsc["build-depends"])
	builddepstr = create_depends_string(builddep)
	filecontents = re_builddep.sub("Build-Depends: "+builddepstr, filecontents)

    if dsc.has_key("build-depends-indep"):
	builddepindstr = create_depends_string(split_depends(dsc["build-depends-indep"]))
	filecontents = re_builddepind.sub("Build-Depends-Indep: "+builddepindstr, filecontents)

    if dsc.has_key("architecture") :
	if (dsc["architecture"] != "any"):
	    newarch = arch_colour + dsc["architecture"] + end_colour
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

		if i[2] == "contrib":
		    result += contrib_colour + d['name']
		elif i[2] == "non-free":
		    result += nonfree_colour + d['name']
		else :
		    result += main_colour + d['name']

		if d['version'] != '' :
		    result += " (%s)" % (d['version'])
		result += end_colour
	    else:
		result += bold_colour + d['name']
		if d['version'] != '' :
		    result += " (%s)" % (d['version'])
		result += end_colour
	    or_count += 1
	comma_count += 1
    return result

def output_deb_info(filename):
    (control, control_keys, section, depends, recommends, arch, maintainer) = read_control(filename)

    if control == '':
	print "no control info"
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
		output += desc
	    else:
		output += control.Find(key)
	    print output

def do_command (command, filename):
    o = os.popen("%s %s" % (command, filename))
    print o.read()

def print_copyright (deb_filename):
    package = re_package.sub(r'\1', deb_filename)
    o = os.popen("dpkg-deb -c %s | egrep 'usr(/share)?/doc/[^/]*/copyright' | awk '{print $6}' | head -n 1" % (deb_filename))
    copyright = o.read()[:-1]

    if copyright == "":
        print "WARNING: No copyright found, please check package manually."
        return

    doc_directory = re_doc_directory.sub(r'\1', copyright)
    if package != doc_directory:
        print "WARNING: wrong doc directory (expected %s, got %s)." % (package, doc_directory)
        return

    o = os.popen("dpkg-deb --fsys-tarfile %s | tar xvOf - %s" % (deb_filename, copyright))
    copyright = o.read()
    copyrightmd5 = md5.md5(copyright).hexdigest()

    if printed_copyrights.has_key(copyrightmd5) and printed_copyrights[copyrightmd5] != "%s (%s)" % (package, deb_filename):
        print "NOTE: Copyright is the same as %s.\n" % \
		(printed_copyrights[copyrightmd5])
    else:
	printed_copyrights[copyrightmd5] = "%s (%s)" % (package, deb_filename)

    print copyright

def check_dsc (dsc_filename):
    print "---- .dsc file for %s ----" % (dsc_filename)
    (dsc) = read_dsc(dsc_filename)
    print dsc
    print "---- lintian check for %s ----" % (dsc_filename)
    do_command("lintian --show-overrides --color always", dsc_filename)

def check_deb (deb_filename):
    filename = os.path.basename(deb_filename)

    if filename.endswith(".udeb"):
	is_a_udeb = 1
    else:
	is_a_udeb = 0

    print "---- control file for %s ----" % (filename)
    #do_command ("dpkg -I", deb_filename)
    output_deb_info(deb_filename)

    if is_a_udeb:
	print "---- skipping lintian check for udeb ----"
	print 
    else:
	print "---- lintian check for %s ----" % (filename)
        do_command ("lintian --show-overrides --color always", deb_filename)
	print "---- linda check for %s ----" % (filename)
        do_command ("linda", deb_filename)

    print "---- contents of %s ----" % (filename)
    do_command ("dpkg -c", deb_filename)

    if is_a_udeb:
	print "---- skipping copyright for udeb ----"
    else:
	print "---- copyright of %s ----" % (filename)
        print_copyright(deb_filename)

    print "---- file listing of %s ----" % (filename)
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
    print "---- .changes file for %s ----" % (changes_filename)
    print strip_pgp_signature(changes_filename)

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

    Arguments = [('h',"help","Examine-Package::Options::Help")]
    for i in [ "help" ]:
	if not Cnf.has_key("Frenanda::Options::%s" % (i)):
	    Cnf["Examine-Package::Options::%s" % (i)] = ""

    args = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Examine-Package::Options")

    if Options["Help"]:
	usage()

    stdout_fd = sys.stdout

    for file in args:
        try:
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

