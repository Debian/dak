#! /usr/bin/env python3

"""
Script to automate some parts of checking NEW packages

Most functions are written in a functional programming style. They
return a string avoiding the side effect of directly printing the string
to stdout. Those functions can be used in multithreaded parts of dak.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
"""

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

import errno
import hashlib
import html
import os
import re
import sys
import apt_pkg
import shutil
import subprocess
import tarfile
import tempfile
import threading
import six

from daklib import utils
from daklib.config import Config
from daklib.dbconn import DBConn, get_component_by_package_suite
from daklib.gpg import SignedFile
from daklib.regexes import re_version, re_spacestrip, \
                           re_contrib, re_nonfree, re_localhost, re_newlinespace, \
                           re_package, re_doc_directory, re_file_binary

################################################################################

Cnf = None
Cnf = utils.get_conf()

printed = threading.local()
printed.copyrights = {}
package_relations = {}           #: Store relations of packages for later output

# default is to not output html.
use_html = False

################################################################################


def usage(exit_code=0):
    print("""Usage: dak examine-package [PACKAGE]...
Check NEW package(s).

  -h, --help                 show this help and exit
  -H, --html-output          output html page with inspection result
  -f, --file-name            filename for the html page

PACKAGE can be a .changes, .dsc, .deb or .udeb filename.""")

    sys.exit(exit_code)

################################################################################
# probably xml.sax.saxutils would work as well


def escape_if_needed(s):
    if use_html:
        return html.escape(s)
    else:
        return s


def headline(s, level=2, bodyelement=None):
    if use_html:
        if bodyelement:
            return """<thead>
                <tr><th colspan="2" class="title" onclick="toggle('%(bodyelement)s', 'table-row-group', 'table-row-group')">%(title)s <span class="toggle-msg">(click to toggle)</span></th></tr>
              </thead>\n""" % {"bodyelement": bodyelement, "title": html.escape(os.path.basename(s), quote=False)}
        else:
            return "<h%d>%s</h%d>\n" % (level, html.escape(s, quote=False), level)
    else:
        return "---- %s ----\n" % (s)


# Colour definitions, 'end' isn't really for use

ansi_colours = {
    'main': "\033[36m",
    'contrib': "\033[33m",
    'nonfree': "\033[31m",
    'provides': "\033[35m",
    'arch': "\033[32m",
    'end': "\033[0m",
    'bold': "\033[1m",
    'maintainer': "\033[32m",
    'distro': "\033[1m\033[41m",
    'error': "\033[1m\033[41m",
    }

html_colours = {
    'main': ('<span style="color: green">', "</span>"),
    'contrib': ('<span style="color: orange">', "</span>"),
    'nonfree': ('<span style="color: red">', "</span>"),
    'provides': ('<span style="color: magenta">', "</span>"),
    'arch': ('<span style="color: green">', "</span>"),
    'bold': ('<span style="font-weight: bold">', "</span>"),
    'maintainer': ('<span style="color: green">', "</span>"),
    'distro': ('<span style="font-weight: bold; background-color: red">', "</span>"),
    'error': ('<span style="font-weight: bold; background-color: red">', "</span>"),
    }


def colour_output(s, colour):
    if use_html:
        return ("%s%s%s" % (html_colours[colour][0], html.escape(s, quote=False), html_colours[colour][1]))
    else:
        return ("%s%s%s" % (ansi_colours[colour], s, ansi_colours['end']))


def escaped_text(s, strip=False):
    if use_html:
        if strip:
            s = s.strip()
        return "<pre>%s</pre>" % (s)
    else:
        return s


def formatted_text(s, strip=False):
    s = six.ensure_str(s)
    if use_html:
        if strip:
            s = s.strip()
        return "<pre>%s</pre>" % (html.escape(s, quote=False))
    else:
        return s


def output_row(s):
    if use_html:
        return """<tr><td>""" + s + """</td></tr>"""
    else:
        return s


def format_field(k, v):
    k = six.ensure_str(k)
    v = six.ensure_str(v)
    if use_html:
        return """<tr><td class="key">%s:</td><td class="val">%s</td></tr>""" % (k, v)
    else:
        return "%s: %s" % (k, v)


def foldable_output(title, elementnameprefix, content, norow=False):
    d = {'elementnameprefix': elementnameprefix}
    result = ''
    if use_html:
        result += """<div id="%(elementnameprefix)s-wrap"><a name="%(elementnameprefix)s" />
                   <table class="infobox rfc822">\n""" % d
    result += headline(title, bodyelement="%(elementnameprefix)s-body" % d)
    if use_html:
        result += """    <tbody id="%(elementnameprefix)s-body" class="infobody">\n""" % d
    if norow:
        result += content + "\n"
    else:
        result += output_row(content) + "\n"
    if use_html:
        result += """</tbody></table></div>"""
    return six.ensure_str(result)

################################################################################


def get_depends_parts(depend):
    v_match = re_version.match(depend)
    if v_match:
        d_parts = {'name': v_match.group(1), 'version': v_match.group(2)}
    else:
        d_parts = {'name': depend, 'version': ''}
    return d_parts


def get_or_list(depend):
    or_list = depend.split("|")
    return or_list


def get_comma_list(depend):
    dep_list = depend.split(",")
    return dep_list


def split_depends(d_str):
    # creates a list of lists of dictionaries of depends (package,version relation)

    d_str = re_spacestrip.sub('', d_str)
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


def read_control(filename):
    recommends = []
    predepends = []
    depends = []
    section = ''
    maintainer = ''
    arch = ''

    try:
        extracts = utils.deb_extract_control(filename)
        control = apt_pkg.TagSection(extracts)
    except:
        print(formatted_text("can't parse control info"))
        raise

    control_keys = list(control.keys())

    if "Pre-Depends" in control:
        predepends_str = control["Pre-Depends"]
        predepends = split_depends(predepends_str)

    if "Depends" in control:
        depends_str = control["Depends"]
        # create list of dependancy lists
        depends = split_depends(depends_str)

    if "Recommends" in control:
        recommends_str = control["Recommends"]
        recommends = split_depends(recommends_str)

    if "Section" in control:
        section_str = control["Section"]

        c_match = re_contrib.search(section_str)
        nf_match = re_nonfree.search(section_str)
        if c_match:
            # contrib colour
            section = colour_output(section_str, 'contrib')
        elif nf_match:
            # non-free colour
            section = colour_output(section_str, 'nonfree')
        else:
            # main
            section = colour_output(section_str, 'main')
    if "Architecture" in control:
        arch_str = control["Architecture"]
        arch = colour_output(arch_str, 'arch')

    if "Maintainer" in control:
        maintainer = control["Maintainer"]
        localhost = re_localhost.search(maintainer)
        if localhost:
            # highlight bad email
            maintainer = colour_output(maintainer, 'maintainer')
        else:
            maintainer = escape_if_needed(maintainer)

    return (control, control_keys, section, predepends, depends, recommends, arch, maintainer)


def read_changes_or_dsc(suite, filename, session=None):
    dsc = {}

    with open(filename) as dsc_file:
        try:
            dsc = utils.parse_changes(filename, dsc_file=1)
        except:
            return formatted_text("can't parse .dsc control info")

    filecontents = six.ensure_str(strip_pgp_signature(filename))
    keysinorder = []
    for l in filecontents.split('\n'):
        m = re.match(r'([-a-zA-Z0-9]*):', l)
        if m:
            keysinorder.append(m.group(1))

    for k in list(dsc.keys()):
        if k in ("build-depends", "build-depends-indep"):
            dsc[k] = create_depends_string(suite, split_depends(dsc[k]), session)
        elif k == "architecture":
            if (dsc["architecture"] != "any"):
                dsc['architecture'] = colour_output(dsc["architecture"], 'arch')
        elif k == "distribution":
            if dsc["distribution"] not in ('unstable', 'experimental'):
                dsc['distribution'] = colour_output(dsc["distribution"], 'distro')
        elif k in ("files", "changes", "description"):
            if use_html:
                dsc[k] = formatted_text(dsc[k], strip=True)
            else:
                dsc[k] = ('\n' + '\n'.join(' ' + x for x in dsc[k].split('\n'))).rstrip()
        else:
            dsc[k] = escape_if_needed(dsc[k])

    filecontents = '\n'.join(format_field(x, dsc[x.lower()])
                             for x in keysinorder if not x.lower().startswith('checksums-')
    ) + '\n'
    return filecontents


def get_provides(suite):
    provides = set()
    session = DBConn().session()
    query = '''SELECT DISTINCT value
               FROM binaries_metadata m
               JOIN bin_associations b
               ON b.bin = m.bin_id
               WHERE key_id = (
                 SELECT key_id
                 FROM metadata_keys
                 WHERE key = 'Provides' )
               AND b.suite = (
                 SELECT id
                 FROM suite
                 WHERE suite_name = '%(suite)s'
                 OR codename = '%(suite)s')''' % \
            {'suite': suite}
    for p in session.execute(query):
        for e in p:
            for i in e.split(','):
                provides.add(i.strip())
    session.close()
    return provides


def create_depends_string(suite, depends_tree, session=None):
    result = ""
    if suite == 'experimental':
        suite_list = ['experimental', 'unstable']
    else:
        suite_list = [suite]

    provides = set()
    comma_count = 1
    for l in depends_tree:
        if (comma_count >= 2):
            result += ", "
        or_count = 1
        for d in l:
            if (or_count >= 2):
                result += " | "
            # doesn't do version lookup yet.

            component = get_component_by_package_suite(d['name'], suite_list,
                session=session)
            if component is not None:
                adepends = d['name']
                if d['version'] != '':
                    adepends += " (%s)" % (d['version'])

                if component == "contrib":
                    result += colour_output(adepends, "contrib")
                elif component == "non-free":
                    result += colour_output(adepends, "nonfree")
                else:
                    result += colour_output(adepends, "main")
            else:
                adepends = d['name']
                if d['version'] != '':
                    adepends += " (%s)" % (d['version'])
                if not provides:
                    provides = get_provides(suite)
                if d['name'] in provides:
                    result += colour_output(adepends, "provides")
                else:
                    result += colour_output(adepends, "bold")
            or_count += 1
        comma_count += 1
    return result


def output_package_relations():
    """
    Output the package relations, if there is more than one package checked in this run.
    """

    if len(package_relations) < 2:
        # Only list something if we have more than one binary to compare
        package_relations.clear()
        result = ""
    else:
        to_print = ""
        for package in package_relations:
            for relation in package_relations[package]:
                to_print += "%-15s: (%s) %s\n" % (package, relation, package_relations[package][relation])

        package_relations.clear()
        result = foldable_output("Package relations", "relations", to_print)
        package_relations.clear()
    return six.ensure_str(result)


def output_deb_info(suite, filename, packagename, session=None):
    (control, control_keys, section, predepends, depends, recommends, arch, maintainer) = read_control(filename)

    if control == '':
        return formatted_text("no control info")
    to_print = ""
    if packagename not in package_relations:
        package_relations[packagename] = {}
    for key in control_keys:
        if key == 'Source':
            field_value = escape_if_needed(control.find(key))
            if use_html:
                field_value = '<a href="https://tracker.debian.org/pkg/{0}" rel="nofollow">{0}</a>'.format(
                              field_value)
        elif key == 'Pre-Depends':
            field_value = create_depends_string(suite, predepends, session)
            package_relations[packagename][key] = field_value
        elif key == 'Depends':
            field_value = create_depends_string(suite, depends, session)
            package_relations[packagename][key] = field_value
        elif key == 'Recommends':
            field_value = create_depends_string(suite, recommends, session)
            package_relations[packagename][key] = field_value
        elif key == 'Section':
            field_value = section
        elif key == 'Architecture':
            field_value = arch
        elif key == 'Maintainer':
            field_value = maintainer
        elif key in ('Homepage', 'Vcs-Browser'):
            field_value = escape_if_needed(control.find(key))
            if use_html:
                field_value = '<a href="%s" rel="nofollow">%s</a>' % \
                    (field_value, field_value)
        elif key == 'Description':
            if use_html:
                field_value = formatted_text(control.find(key), strip=True)
            else:
                desc = control.find(key)
                desc = re_newlinespace.sub('\n ', desc)
                field_value = escape_if_needed(desc)
        else:
            field_value = escape_if_needed(control.find(key))
        to_print += " " + format_field(key, field_value) + '\n'
    return to_print


def do_command(command, escaped=False):
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    data = six.ensure_str(process.communicate()[0])
    if escaped:
        return escaped_text(data)
    else:
        return formatted_text(data)


def do_lintian(filename):
    cnf = Config()
    cmd = []

    user = cnf.get('Dinstall::UnprivUser') or None
    if user is not None:
        cmd.extend(['sudo', '-H', '-u', user])

    color = 'always'
    if use_html:
        color = 'html'

    cmd.extend(['lintian', '--show-overrides', '--color', color, "--", filename])

    try:
        return do_command(cmd, escaped=True)
    except OSError as e:
        return (colour_output("Running lintian failed: %s" % (e), "error"))


def extract_one_file_from_deb(deb_filename, match):
    with tempfile.TemporaryFile() as tmpfh:
        dpkg_cmd = ('dpkg-deb', '--fsys-tarfile', deb_filename)
        subprocess.check_call(dpkg_cmd, stdout=tmpfh)

        tmpfh.seek(0)
        with tarfile.open(fileobj=tmpfh, mode="r") as tar:
            matched_member = None
            for member in tar:
                if member.isfile() and match.match(member.name):
                    matched_member = member
                    break

            if not matched_member:
                return None, None

            fh = tar.extractfile(matched_member)
            matched_data = fh.read()
            fh.close()

            return matched_member.name, matched_data


def get_copyright(deb_filename):
    global printed

    re_copyright = re.compile(r"\./usr(/share)?/doc/(?P<package>[^/]+)/copyright")
    cright_path, cright = extract_one_file_from_deb(deb_filename, re_copyright)

    if not cright_path:
        return formatted_text("WARNING: No copyright found, please check package manually.")

    package = re_file_binary.match(os.path.basename(deb_filename)).group('package')
    doc_directory = re_copyright.match(cright_path).group('package')
    if package != doc_directory:
        return formatted_text("WARNING: wrong doc directory (expected %s, got %s)." % (package, doc_directory))

    copyrightmd5 = hashlib.md5(cright).hexdigest()

    res = ""
    if copyrightmd5 in printed.copyrights and printed.copyrights[copyrightmd5] != "%s (%s)" % (package, os.path.basename(deb_filename)):
        res += formatted_text("NOTE: Copyright is the same as %s.\n\n" %
                               (printed.copyrights[copyrightmd5]))
    else:
        printed.copyrights[copyrightmd5] = "%s (%s)" % (package, os.path.basename(deb_filename))
    return res + formatted_text(cright)


def get_readme_source(dsc_filename):
    with tempfile.TemporaryDirectory(prefix="dak-examine-package") as tempdir:
        targetdir = os.path.join(tempdir, "source")

        cmd = ('dpkg-source', '--no-check', '--no-copy', '-x', dsc_filename, targetdir)
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            res = "How is education supposed to make me feel smarter? Besides, every time I learn something new, it pushes some\n old stuff out of my brain. Remember when I took that home winemaking course, and I forgot how to drive?\n"
            res += "Error, couldn't extract source, WTF?\n"
            res += "'dpkg-source -x' failed. return code: %s.\n\n" % (e.returncode)
            res += e.output
            return res

        path = os.path.join(targetdir, 'debian/README.source')
        res = ""
        if os.path.exists(path):
            with open(path, 'r') as fh:
                res += formatted_text(fh.read())
        else:
            res += "No README.source in this package\n\n"

    return six.ensure_str(res)


def check_dsc(suite, dsc_filename, session=None):
    dsc_filename = six.ensure_str(dsc_filename)
    dsc = read_changes_or_dsc(suite, dsc_filename, session)
    dsc_basename = os.path.basename(dsc_filename)
    cdsc = foldable_output(dsc_filename, "dsc", dsc, norow=True) + \
           "\n" + \
           foldable_output("lintian {} check for {}".format(
                get_lintian_version(), dsc_basename),
               "source-lintian", do_lintian(dsc_filename)) + \
           "\n" + \
           foldable_output("README.source for %s" % dsc_basename,
               "source-readmesource", get_readme_source(dsc_filename))
    return six.ensure_str(cdsc)


def check_deb(suite, deb_filename, session=None):
    filename = six.ensure_str(os.path.basename(deb_filename))
    packagename = filename.split('_')[0]

    if filename.endswith(".udeb"):
        is_a_udeb = 1
    else:
        is_a_udeb = 0

    result = foldable_output("control file for %s" % (filename), "binary-%s-control" % packagename,
        output_deb_info(suite, deb_filename, packagename, session), norow=True) + "\n"

    if is_a_udeb:
        result += foldable_output("skipping lintian check for udeb",
            "binary-%s-lintian" % packagename, "") + "\n"
    else:
        result += foldable_output("lintian {} check for {}".format(
                                  get_lintian_version(), filename),
            "binary-%s-lintian" % packagename, do_lintian(deb_filename)) + "\n"

    result += foldable_output("contents of %s" % (filename), "binary-%s-contents" % packagename,
                              do_command(["dpkg", "-c", deb_filename])) + "\n"

    if is_a_udeb:
        result += foldable_output("skipping copyright for udeb",
            "binary-%s-copyright" % packagename, "") + "\n"
    else:
        result += foldable_output("copyright of %s" % (filename),
            "binary-%s-copyright" % packagename, get_copyright(deb_filename)) + "\n"

    return six.ensure_str(result)

# Read a file, strip the signature and return the modified contents as
# a string.


def strip_pgp_signature(filename):
    with open(filename, 'rb') as f:
        data = f.read()
        signedfile = SignedFile(data, keyrings=(), require_signature=False)
        return signedfile.contents


def display_changes(suite, changes_filename):
    global printed
    changes = read_changes_or_dsc(suite, changes_filename)
    printed.copyrights = {}
    return six.ensure_str(foldable_output(changes_filename, "changes", changes, norow=True))


def check_changes(changes_filename):
    try:
        changes = utils.parse_changes(changes_filename)
    except UnicodeDecodeError:
        utils.warn("Encoding problem with changes file %s" % (changes_filename))
    output = display_changes(changes['distribution'], changes_filename)

    files = utils.build_file_list(changes)
    for f in files.keys():
        if f.endswith(".deb") or f.endswith(".udeb"):
            output += check_deb(changes['distribution'], f)
        if f.endswith(".dsc"):
            output += check_dsc(changes['distribution'], f)
        # else: => byhand
    return six.ensure_str(output)


def main():
    global Cnf, db_files, waste, excluded

#    Cnf = utils.get_conf()

    Arguments = [('h', "help", "Examine-Package::Options::Help"),
                 ('H', "html-output", "Examine-Package::Options::Html-Output"),
                ]
    for i in ["Help", "Html-Output", "partial-html"]:
        key = "Examine-Package::Options::%s" % i
        if key not in Cnf:
            Cnf[key] = ""

    args = apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)
    Options = Cnf.subtree("Examine-Package::Options")

    if Options["Help"]:
        usage()

    if Options["Html-Output"]:
        global use_html
        use_html = True

    for f in args:
        try:
            if not Options["Html-Output"]:
                # Pipe output for each argument through less
                less_cmd = ("less", "-r", "-")
                less_process = subprocess.Popen(less_cmd, stdin=subprocess.PIPE, bufsize=0)
                less_fd = less_process.stdin
                # -R added to display raw control chars for colour
                my_fd = less_fd
            else:
                my_fd = sys.stdout

            try:
                if f.endswith(".changes"):
                    my_fd.write(six.ensure_binary(check_changes(f)))
                elif f.endswith(".deb") or f.endswith(".udeb"):
                    # default to unstable when we don't have a .changes file
                    # perhaps this should be a command line option?
                    my_fd.write(six.ensure_binary(check_deb('unstable', f)))
                elif f.endswith(".dsc"):
                    my_fd.write(six.ensure_binary(check_dsc('unstable', f)))
                else:
                    utils.fubar("Unrecognised file type: '%s'." % (f))
            finally:
                my_fd.write(six.ensure_binary(output_package_relations()))
                if not Options["Html-Output"]:
                    # Reset stdout here so future less invocations aren't FUBAR
                    less_fd.close()
                    less_process.wait()
        except IOError as e:
            if e.errno == errno.EPIPE:
                utils.warn("[examine-package] Caught EPIPE; skipping.")
                pass
            else:
                raise
        except KeyboardInterrupt:
            utils.warn("[examine-package] Caught C-c; skipping.")
            pass


def get_lintian_version():
    if not hasattr(get_lintian_version, '_version'):
        # eg. "Lintian v2.5.100"
        val = subprocess.check_output(('lintian', '--version'))
        get_lintian_version._version = six.ensure_str(val).split(' v')[-1].strip()

    return get_lintian_version._version


#######################################################################################

if __name__ == '__main__':
    main()
