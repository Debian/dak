# vim:set et ts=4 sw=4:

"""Utility functions

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
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

import datetime
import os
import pwd
import grp
import shutil
import sqlalchemy.sql as sql
import sys
import tempfile
import apt_inst
import apt_pkg
import re
import email as modemail
import subprocess
import errno
import functools
import six

import daklib.config as config
from .dbconn import DBConn, get_architecture, get_component, get_suite, \
                   get_active_keyring_paths, \
                   get_suite_architectures, get_or_set_metadatakey, \
                   Component, Override, OverrideType
from .dak_exceptions import *
from .gpg import SignedFile
from .textutils import fix_maintainer
from .regexes import re_single_line_field, \
                    re_multi_line_field, re_srchasver, \
                    re_re_mark, re_whitespace_comment, re_issource, \
                    re_build_dep_arch, re_parse_maintainer

from .formats import parse_format, validate_changes_format
from .srcformats import get_format_from_string
from collections import defaultdict

################################################################################

default_config = "/etc/dak/dak.conf"     #: default dak config, defines host properties

alias_cache = None        #: Cache for email alias checks
key_uid_email_cache = {}  #: Cache for email addresses from gpg key uids

################################################################################


def our_raw_input(prompt=""):
    if prompt:
        print(prompt)
    # TODO: py3: use `print(..., flush=True)`
    sys.stdout.flush()
    try:
        return input()
    except EOFError:
        print("\nUser interrupt (^D).", file=sys.stderr)
        raise SystemExit

################################################################################


def extract_component_from_section(section):
    component = ""

    if section.find('/') != -1:
        component = section.split('/')[0]

    # Expand default component
    if component == "":
        component = "main"

    return (section, component)

################################################################################


def parse_deb822(armored_contents, signing_rules=0, keyrings=None):
    require_signature = True
    if keyrings is None:
        keyrings = []
        require_signature = False

    signed_file = SignedFile(armored_contents.encode('utf-8'), keyrings=keyrings, require_signature=require_signature)
    contents = signed_file.contents.decode('utf-8')

    error = ""
    changes = {}

    # Split the lines in the input, keeping the linebreaks.
    lines = contents.splitlines(True)

    if len(lines) == 0:
        raise ParseChangesError("[Empty changes file]")

    # Reindex by line number so we can easily verify the format of
    # .dsc files...
    index = 0
    indexed_lines = {}
    for line in lines:
        index += 1
        indexed_lines[index] = line[:-1]

    num_of_lines = len(indexed_lines)
    index = 0
    first = -1
    while index < num_of_lines:
        index += 1
        line = indexed_lines[index]
        if line == "" and signing_rules == 1:
            if index != num_of_lines:
                raise InvalidDscError(index)
            break
        slf = re_single_line_field.match(line)
        if slf:
            field = slf.groups()[0].lower()
            changes[field] = slf.groups()[1]
            first = 1
            continue
        if line == " .":
            changes[field] += '\n'
            continue
        mlf = re_multi_line_field.match(line)
        if mlf:
            if first == -1:
                raise ParseChangesError("'%s'\n [Multi-line field continuing on from nothing?]" % (line))
            if first == 1 and changes[field] != "":
                changes[field] += '\n'
            first = 0
            changes[field] += mlf.groups()[0] + '\n'
            continue
        error += line

    changes["filecontents"] = armored_contents

    if "source" in changes:
        # Strip the source version in brackets from the source field,
        # put it in the "source-version" field instead.
        srcver = re_srchasver.search(changes["source"])
        if srcver:
            changes["source"] = srcver.group(1)
            changes["source-version"] = srcver.group(2)

    if error:
        raise ParseChangesError(error)

    return changes

################################################################################


def parse_changes(filename, signing_rules=0, dsc_file=0, keyrings=None):
    """
    Parses a changes file and returns a dictionary where each field is a
    key.  The mandatory first argument is the filename of the .changes
    file.

    signing_rules is an optional argument:

      - If signing_rules == -1, no signature is required.
      - If signing_rules == 0 (the default), a signature is required.
      - If signing_rules == 1, it turns on the same strict format checking
        as dpkg-source.

    The rules for (signing_rules == 1)-mode are:

      - The PGP header consists of "-----BEGIN PGP SIGNED MESSAGE-----"
        followed by any PGP header data and must end with a blank line.

      - The data section must end with a blank line and must be followed by
        "-----BEGIN PGP SIGNATURE-----".
    """

    with open(filename, 'r', encoding='utf-8') as changes_in:
        content = changes_in.read()
    changes = parse_deb822(content, signing_rules, keyrings=keyrings)

    if not dsc_file:
        # Finally ensure that everything needed for .changes is there
        must_keywords = ('Format', 'Date', 'Source', 'Architecture', 'Version',
                         'Distribution', 'Maintainer', 'Changes', 'Files')

        missingfields = []
        for keyword in must_keywords:
            if keyword.lower() not in changes:
                missingfields.append(keyword)

                if len(missingfields):
                    raise ParseChangesError("Missing mandatory field(s) in changes file (policy 5.5): %s" % (missingfields))

    return changes


################################################################################


def check_dsc_files(dsc_filename, dsc, dsc_files):
    """
    Verify that the files listed in the Files field of the .dsc are
    those expected given the announced Format.

    @type dsc_filename: string
    @param dsc_filename: path of .dsc file

    @type dsc: dict
    @param dsc: the content of the .dsc parsed by C{parse_changes()}

    @type dsc_files: dict
    @param dsc_files: the file list returned by C{build_file_list()}

    @rtype: list
    @return: all errors detected
    """
    rejmsg = []

    # Ensure .dsc lists proper set of source files according to the format
    # announced
    has = defaultdict(lambda: 0)

    ftype_lookup = (
        (r'orig\.tar\.(gz|bz2|xz)\.asc', ('orig_tar_sig',)),
        (r'orig\.tar\.gz',             ('orig_tar_gz', 'orig_tar')),
        (r'diff\.gz',                  ('debian_diff',)),
        (r'tar\.gz',                   ('native_tar_gz', 'native_tar')),
        (r'debian\.tar\.(gz|bz2|xz)',  ('debian_tar',)),
        (r'orig\.tar\.(gz|bz2|xz)',    ('orig_tar',)),
        (r'tar\.(gz|bz2|xz)',          ('native_tar',)),
        (r'orig-.+\.tar\.(gz|bz2|xz)\.asc', ('more_orig_tar_sig',)),
        (r'orig-.+\.tar\.(gz|bz2|xz)', ('more_orig_tar',)),
    )

    for f in dsc_files:
        m = re_issource.match(f)
        if not m:
            rejmsg.append("%s: %s in Files field not recognised as source."
                          % (dsc_filename, f))
            continue

        # Populate 'has' dictionary by resolving keys in lookup table
        matched = False
        for regex, keys in ftype_lookup:
            if re.match(regex, m.group(3)):
                matched = True
                for key in keys:
                    has[key] += 1
                break

        # File does not match anything in lookup table; reject
        if not matched:
            rejmsg.append("%s: unexpected source file '%s'" % (dsc_filename, f))
            break

    # Check for multiple files
    for file_type in ('orig_tar', 'orig_tar_sig', 'native_tar', 'debian_tar', 'debian_diff'):
        if has[file_type] > 1:
            rejmsg.append("%s: lists multiple %s" % (dsc_filename, file_type))

    # Source format specific tests
    try:
        format = get_format_from_string(dsc['format'])
        rejmsg.extend([
            '%s: %s' % (dsc_filename, x) for x in format.reject_msgs(has)
        ])

    except UnknownFormatError:
        # Not an error here for now
        pass

    return rejmsg

################################################################################

# Dropped support for 1.4 and ``buggy dchanges 3.4'' (?!) compared to di.pl


def build_file_list(changes, is_a_dsc=0, field="files", hashname="md5sum"):
    files = {}

    # Make sure we have a Files: field to parse...
    if field not in changes:
        raise NoFilesFieldError

    # Validate .changes Format: field
    if not is_a_dsc:
        validate_changes_format(parse_format(changes['format']), field)

    includes_section = (not is_a_dsc) and field == "files"

    # Parse each entry/line:
    for i in changes[field].split('\n'):
        if not i:
            break
        s = i.split()
        section = priority = ""
        try:
            if includes_section:
                (md5, size, section, priority, name) = s
            else:
                (md5, size, name) = s
        except ValueError:
            raise ParseChangesError(i)

        if section == "":
            section = "-"
        if priority == "":
            priority = "-"

        (section, component) = extract_component_from_section(section)

        files[name] = dict(size=size, section=section,
                           priority=priority, component=component)
        files[name][hashname] = md5

    return files

################################################################################


def send_mail(message, filename="", whitelists=None):
    """sendmail wrapper, takes _either_ a message string or a file as arguments

    @type  whitelists: list of (str or None)
    @param whitelists: path to whitelists. C{None} or an empty list whitelists
                       everything, otherwise an address is whitelisted if it is
                       included in any of the lists.
                       In addition a global whitelist can be specified in
                       Dinstall::MailWhiteList.
    """

    maildir = Cnf.get('Dir::Mail')
    if maildir:
        path = os.path.join(maildir, datetime.datetime.now().isoformat())
        path = find_next_free(path)
        with open(path, 'w') as fh:
            print(message, end=' ', file=fh)

    # Check whether we're supposed to be sending mail
    if "Dinstall::Options::No-Mail" in Cnf and Cnf["Dinstall::Options::No-Mail"]:
        return

    # If we've been passed a string dump it into a temporary file
    if message:
        (fd, filename) = tempfile.mkstemp()
        with os.fdopen(fd, 'wt') as f:
            f.write(message)

    if whitelists is None or None in whitelists:
        whitelists = []
    if Cnf.get('Dinstall::MailWhiteList', ''):
        whitelists.append(Cnf['Dinstall::MailWhiteList'])
    if len(whitelists) != 0:
        with open(filename) as message_in:
            message_raw = modemail.message_from_file(message_in)

        whitelist = []
        for path in whitelists:
            with open(path, 'r') as whitelist_in:
                for line in whitelist_in:
                    if not re_whitespace_comment.match(line):
                        if re_re_mark.match(line):
                            whitelist.append(re.compile(re_re_mark.sub("", line.strip(), 1)))
                        else:
                            whitelist.append(re.compile(re.escape(line.strip())))

        # Fields to check.
        fields = ["To", "Bcc", "Cc"]
        for field in fields:
            # Check each field
            value = message_raw.get(field, None)
            if value is not None:
                match = []
                for item in value.split(","):
                    (rfc822_maint, rfc2047_maint, name, email) = fix_maintainer(item.strip())
                    mail_whitelisted = 0
                    for wr in whitelist:
                        if wr.match(email):
                            mail_whitelisted = 1
                            break
                    if not mail_whitelisted:
                        print("Skipping {0} since it's not whitelisted".format(item))
                        continue
                    match.append(item)

                # Doesn't have any mail in whitelist so remove the header
                if len(match) == 0:
                    del message_raw[field]
                else:
                    message_raw.replace_header(field, ', '.join(match))

        # Change message fields in order if we don't have a To header
        if "To" not in message_raw:
            fields.reverse()
            for field in fields:
                if field in message_raw:
                    message_raw[fields[-1]] = message_raw[field]
                    del message_raw[field]
                    break
            else:
                # Clean up any temporary files
                # and return, as we removed all recipients.
                if message:
                    os.unlink(filename)
                return

        fd = os.open(filename, os.O_RDWR | os.O_EXCL, 0o700)
        with os.fdopen(fd, 'wt') as f:
            f.write(message_raw.as_string(True))

    # Invoke sendmail
    try:
        with open(filename, 'r') as fh:
            subprocess.check_output(Cnf["Dinstall::SendmailCommand"].split(), stdin=fh, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise SendmailFailedError(e.output.rstrip())

    # Clean up any temporary files
    if message:
        os.unlink(filename)

################################################################################


def poolify(source):
    if source[:3] == "lib":
        return source[:4] + '/' + source + '/'
    else:
        return source[:1] + '/' + source + '/'

################################################################################


def move(src, dest, overwrite=0, perms=0o664):
    if os.path.exists(dest) and os.path.isdir(dest):
        dest_dir = dest
    else:
        dest_dir = os.path.dirname(dest)
    if not os.path.lexists(dest_dir):
        umask = os.umask(00000)
        os.makedirs(dest_dir, 0o2775)
        os.umask(umask)
    # print "Moving %s to %s..." % (src, dest)
    if os.path.exists(dest) and os.path.isdir(dest):
        dest += '/' + os.path.basename(src)
    # Don't overwrite unless forced to
    if os.path.lexists(dest):
        if not overwrite:
            fubar("Can't move %s to %s - file already exists." % (src, dest))
        else:
            if not os.access(dest, os.W_OK):
                fubar("Can't move %s to %s - can't write to existing file." % (src, dest))
    shutil.copy2(src, dest)
    os.chmod(dest, perms)
    os.unlink(src)


################################################################################


def TemplateSubst(subst_map, filename):
    """ Perform a substition of template """
    with open(filename) as templatefile:
        template = templatefile.read()
    for k, v in subst_map.items():
        template = template.replace(k, str(v))
    return template

################################################################################


def fubar(msg, exit_code=1):
    print("E:", msg, file=sys.stderr)
    sys.exit(exit_code)


def warn(msg):
    print("W:", msg, file=sys.stderr)

################################################################################

# Returns the user name with a laughable attempt at rfc822 conformancy
# (read: removing stray periods).


def whoami():
    return pwd.getpwuid(os.getuid())[4].split(',')[0].replace('.', '')


def getusername():
    return pwd.getpwuid(os.getuid())[0]

################################################################################


def size_type(c):
    t = " B"
    if c > 10240:
        c = c / 1024
        t = " KB"
    if c > 10240:
        c = c / 1024
        t = " MB"
    return ("%d%s" % (c, t))

################################################################################


def find_next_free(dest, too_many=100):
    extra = 0
    orig_dest = dest
    while os.path.lexists(dest) and extra < too_many:
        dest = orig_dest + '.' + repr(extra)
        extra += 1
    if extra >= too_many:
        raise NoFreeFilenameError
    return dest

################################################################################


def result_join(original, sep='\t'):
    return sep.join(
        x if x is not None else ""
        for x in original
    )


################################################################################


def prefix_multi_line_string(str, prefix, include_blank_lines=0):
    out = ""
    for line in str.split('\n'):
        line = line.strip()
        if line or include_blank_lines:
            out += "%s%s\n" % (prefix, line)
    # Strip trailing new line
    if out:
        out = out[:-1]
    return out

################################################################################


def join_with_commas_and(list):
    if len(list) == 0:
        return "nothing"
    if len(list) == 1:
        return list[0]
    return ", ".join(list[:-1]) + " and " + list[-1]

################################################################################


def pp_deps(deps):
    pp_deps = []
    for atom in deps:
        (pkg, version, constraint) = atom
        if constraint:
            pp_dep = "%s (%s %s)" % (pkg, constraint, version)
        else:
            pp_dep = pkg
        pp_deps.append(pp_dep)
    return " |".join(pp_deps)

################################################################################


def get_conf():
    return Cnf

################################################################################


def parse_args(Options):
    """ Handle -a, -c and -s arguments; returns them as SQL constraints """
    # XXX: This should go away and everything which calls it be converted
    #      to use SQLA properly.  For now, we'll just fix it not to use
    #      the old Pg interface though
    session = DBConn().session()
    # Process suite
    if Options["Suite"]:
        suite_ids_list = []
        for suitename in split_args(Options["Suite"]):
            suite = get_suite(suitename, session=session)
            if not suite or suite.suite_id is None:
                warn("suite '%s' not recognised." % (suite and suite.suite_name or suitename))
            else:
                suite_ids_list.append(suite.suite_id)
        if suite_ids_list:
            con_suites = "AND su.id IN (%s)" % ", ".join([str(i) for i in suite_ids_list])
        else:
            fubar("No valid suite given.")
    else:
        con_suites = ""

    # Process component
    if Options["Component"]:
        component_ids_list = []
        for componentname in split_args(Options["Component"]):
            component = get_component(componentname, session=session)
            if component is None:
                warn("component '%s' not recognised." % (componentname))
            else:
                component_ids_list.append(component.component_id)
        if component_ids_list:
            con_components = "AND c.id IN (%s)" % ", ".join([str(i) for i in component_ids_list])
        else:
            fubar("No valid component given.")
    else:
        con_components = ""

    # Process architecture
    con_architectures = ""
    check_source = 0
    if Options["Architecture"]:
        arch_ids_list = []
        for archname in split_args(Options["Architecture"]):
            if archname == "source":
                check_source = 1
            else:
                arch = get_architecture(archname, session=session)
                if arch is None:
                    warn("architecture '%s' not recognised." % (archname))
                else:
                    arch_ids_list.append(arch.arch_id)
        if arch_ids_list:
            con_architectures = "AND a.id IN (%s)" % ", ".join([str(i) for i in arch_ids_list])
        else:
            if not check_source:
                fubar("No valid architecture given.")
    else:
        check_source = 1

    return (con_suites, con_architectures, con_components, check_source)

################################################################################


@functools.total_ordering
class ArchKey(object):
    """
    Key object for use in sorting lists of architectures.

    Sorts normally except that 'source' dominates all others.
    """

    __slots__ = ['arch', 'issource']

    def __init__(self, arch, *args):
        self.arch = arch
        self.issource = arch == 'source'

    def __lt__(self, other):
        if self.issource:
            return not other.issource
        if other.issource:
            return False
        return self.arch < other.arch

    def __eq__(self, other):
        return self.arch == other.arch


################################################################################


def split_args(s, dwim=True):
    """
    Split command line arguments which can be separated by either commas
    or whitespace.  If dwim is set, it will complain about string ending
    in comma since this usually means someone did 'dak ls -a i386, m68k
    foo' or something and the inevitable confusion resulting from 'm68k'
    being treated as an argument is undesirable.
    """

    if s.find(",") == -1:
        return s.split()
    else:
        if s[-1:] == "," and dwim:
            fubar("split_args: found trailing comma, spurious space maybe?")
        return s.split(",")

################################################################################


def gpg_keyring_args(keyrings=None):
    if not keyrings:
        keyrings = get_active_keyring_paths()

    return ["--keyring={}".format(path) for path in keyrings]

################################################################################


def _gpg_get_addresses_from_listing(output: bytes):
    addresses = []

    for line in output.split(b'\n'):
        parts = line.split(b':')
        if parts[0] not in (b"uid", b"pub"):
            continue
        if parts[1] in (b"i", b"d", b"r"):
            # Skip uid that is invalid, disabled or revoked
            continue
        try:
            uid = parts[9]
        except IndexError:
            continue
        try:
            uid = uid.decode(encoding='utf-8')
        except UnicodeDecodeError:
            # If the uid is not valid UTF-8, we assume it is an old uid
            # still encoding in Latin-1.
            uid = uid.decode(encoding='latin1')
        m = re_parse_maintainer.match(uid)
        if not m:
            continue
        address = m.group(2)
        address = six.ensure_str(address)
        if address.endswith('@debian.org'):
            # prefer @debian.org addresses
            # TODO: maybe not hardcode the domain
            addresses.insert(0, address)
        else:
            addresses.append(address)

    return addresses


def gpg_get_key_addresses(fingerprint):
    """retreive email addresses from gpg key uids for a given fingerprint"""
    addresses = key_uid_email_cache.get(fingerprint)
    if addresses is not None:
        return addresses

    try:
        cmd = ["gpg", "--no-default-keyring"]
        cmd.extend(gpg_keyring_args())
        cmd.extend(["--with-colons", "--list-keys", "--", fingerprint])
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        addresses = []
    else:
        addresses = _gpg_get_addresses_from_listing(output)

    key_uid_email_cache[fingerprint] = addresses
    return addresses

################################################################################


def open_ldap_connection():
    """open connection to the configured LDAP server"""
    import ldap

    LDAPDn = Cnf["Import-LDAP-Fingerprints::LDAPDn"]
    LDAPServer = Cnf["Import-LDAP-Fingerprints::LDAPServer"]
    ca_cert_file = Cnf.get('Import-LDAP-Fingerprints::CACertFile')

    l = ldap.initialize(LDAPServer)

    if ca_cert_file:
        l.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_HARD)
        l.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
        l.set_option(ldap.OPT_X_TLS_NEWCTX, True)
        l.start_tls_s()

    l.simple_bind_s("", "")

    return l

################################################################################


def get_logins_from_ldap(fingerprint='*'):
    """retrieve login from LDAP linked to a given fingerprint"""
    import ldap
    l = open_ldap_connection()
    LDAPDn = Cnf["Import-LDAP-Fingerprints::LDAPDn"]
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       '(keyfingerprint=%s)' % fingerprint,
                       ['uid', 'keyfingerprint'])
    login = {}
    for elem in Attrs:
        fpr = six.ensure_str(elem[1]['keyFingerPrint'][0])
        uid = six.ensure_str(elem[1]['uid'][0])
        login[fpr] = uid
    return login

################################################################################


def get_users_from_ldap():
    """retrieve login and user names from LDAP"""
    import ldap
    l = open_ldap_connection()
    LDAPDn = Cnf["Import-LDAP-Fingerprints::LDAPDn"]
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       '(uid=*)', ['uid', 'cn', 'mn', 'sn'])
    users = {}
    for elem in Attrs:
        elem = elem[1]
        name = []
        for k in ('cn', 'mn', 'sn'):
            try:
                value = six.ensure_str(elem[k][0])
                if value and value[0] != '-':
                    name.append(value)
            except KeyError:
                pass
        users[' '.join(name)] = elem['uid'][0]
    return users

################################################################################


def clean_symlink(src, dest, root):
    """
    Relativize an absolute symlink from 'src' -> 'dest' relative to 'root'.
    Returns fixed 'src'
    """
    src = src.replace(root, '', 1)
    dest = dest.replace(root, '', 1)
    dest = os.path.dirname(dest)
    new_src = '../' * len(dest.split('/'))
    return new_src + src

################################################################################


def temp_dirname(parent=None, prefix="dak", suffix="", mode=None, group=None):
    """
    Return a secure and unique directory by pre-creating it.

    @type parent: str
    @param parent: If non-null it will be the directory the directory is pre-created in.

    @type prefix: str
    @param prefix: The filename will be prefixed with this string

    @type suffix: str
    @param suffix: The filename will end with this string

    @type mode: str
    @param mode: If set the file will get chmodded to those permissions

    @type group: str
    @param group: If set the file will get chgrped to the specified group.

    @rtype: list
    @return: Returns a pair (fd, name)

    """

    tfname = tempfile.mkdtemp(suffix, prefix, parent)
    if mode:
        os.chmod(tfname, mode)
    if group:
        gid = grp.getgrnam(group).gr_gid
        os.chown(tfname, -1, gid)
    return tfname


################################################################################


def get_changes_files(from_dir):
    """
    Takes a directory and lists all .changes files in it (as well as chdir'ing
    to the directory; this is due to broken behaviour on the part of p-u/p-a
    when you're not in the right place)

    Returns a list of filenames
    """
    try:
        # Much of the rest of p-u/p-a depends on being in the right place
        os.chdir(from_dir)
        changes_files = [x for x in os.listdir(from_dir) if x.endswith('.changes')]
    except OSError as e:
        fubar("Failed to read list from directory %s (%s)" % (from_dir, e))

    return changes_files

################################################################################


Cnf = config.Config().Cnf

################################################################################


def parse_wnpp_bug_file(file="/srv/ftp-master.debian.org/scripts/masterfiles/wnpp_rm"):
    """
    Parses the wnpp bug list available at https://qa.debian.org/data/bts/wnpp_rm
    Well, actually it parsed a local copy, but let's document the source
    somewhere ;)

    returns a dict associating source package name with a list of open wnpp
    bugs (Yes, there might be more than one)
    """

    try:
        with open(file) as f:
            lines = f.readlines()
    except IOError:
        print("Warning:  Couldn't open %s; don't know about WNPP bugs, so won't close any." % file)
        lines = []
    wnpp = {}

    for line in lines:
        splited_line = line.split(": ", 1)
        if len(splited_line) > 1:
            wnpp[splited_line[0]] = splited_line[1].split("|")

    for source in wnpp:
        bugs = []
        for wnpp_bug in wnpp[source]:
            bug_no = re.search(r"(\d)+", wnpp_bug).group()
            if bug_no:
                bugs.append(bug_no)
        wnpp[source] = bugs
    return wnpp

################################################################################


def deb_extract_control(path):
    """extract DEBIAN/control from a binary package"""
    return apt_inst.DebFile(path).control.extractdata("control")

################################################################################


def mail_addresses_for_upload(maintainer, changed_by, fingerprint):
    """mail addresses to contact for an upload

    @type  maintainer: str
    @param maintainer: Maintainer field of the .changes file

    @type  changed_by: str
    @param changed_by: Changed-By field of the .changes file

    @type  fingerprint: str
    @param fingerprint: fingerprint of the key used to sign the upload

    @rtype:  list of str
    @return: list of RFC 2047-encoded mail addresses to contact regarding
             this upload
    """
    recipients = Cnf.value_list('Dinstall::UploadMailRecipients')
    if not recipients:
        recipients = [
            'maintainer',
            'changed_by',
            'signer',
        ]

    # Ensure signer is last if present
    try:
        recipients.remove('signer')
        recipients.append('signer')
    except ValueError:
        pass

    # Compute the set of addresses of the recipients
    addresses = set()  # Name + email
    emails = set()     # Email only, used to avoid duplicates
    for recipient in recipients:
        if recipient.startswith('mail:'):  # Email hardcoded in config
            address = recipient[5:]
        elif recipient == 'maintainer':
            address = maintainer
        elif recipient == 'changed_by':
            address = changed_by
        elif recipient == 'signer':
            fpr_addresses = gpg_get_key_addresses(fingerprint)
            address = fpr_addresses[0] if fpr_addresses else None
            if any(x in emails for x in fpr_addresses):
                # The signer already gets a copy via another email
                address = None
        else:
            raise Exception('Unsupported entry in {0}: {1}'.format(
                'Dinstall::UploadMailRecipients', recipient))

        if address is not None:
            email = fix_maintainer(address)[3]
            if email not in emails:
                addresses.add(address)
                emails.add(email)

    encoded_addresses = [fix_maintainer(e)[1] for e in addresses]
    return encoded_addresses

################################################################################


def call_editor_for_file(path):
    editor = os.environ.get('VISUAL', os.environ.get('EDITOR', 'sensible-editor'))
    subprocess.check_call([editor, path])

################################################################################


def call_editor(text="", suffix=".txt"):
    """run editor and return the result as a string

    @type  text: str
    @param text: initial text

    @type  suffix: str
    @param suffix: extension for temporary file

    @rtype:  str
    @return: string with the edited text
    """
    with tempfile.NamedTemporaryFile(mode='w+t', suffix=suffix) as fh:
        print(text, end='', file=fh)
        fh.flush()
        call_editor_for_file(fh.name)
        fh.seek(0)
        return fh.read()

################################################################################


def check_reverse_depends(removals, suite, arches=None, session=None, cruft=False, quiet=False, include_arch_all=True):
    dbsuite = get_suite(suite, session)
    overridesuite = dbsuite
    if dbsuite.overridesuite is not None:
        overridesuite = get_suite(dbsuite.overridesuite, session)
    dep_problem = 0
    p2c = {}
    all_broken = defaultdict(lambda: defaultdict(set))
    if arches:
        all_arches = set(arches)
    else:
        all_arches = set(x.arch_string for x in get_suite_architectures(suite))
    all_arches -= set(["source", "all"])
    removal_set = set(removals)
    metakey_d = get_or_set_metadatakey("Depends", session)
    metakey_p = get_or_set_metadatakey("Provides", session)
    params = {
        'suite_id':     dbsuite.suite_id,
        'metakey_d_id': metakey_d.key_id,
        'metakey_p_id': metakey_p.key_id,
    }
    if include_arch_all:
        rdep_architectures = all_arches | set(['all'])
    else:
        rdep_architectures = all_arches
    for architecture in rdep_architectures:
        deps = {}
        sources = {}
        virtual_packages = {}
        try:
            params['arch_id'] = get_architecture(architecture, session).arch_id
        except AttributeError:
            continue

        statement = sql.text('''
            SELECT b.package, s.source, c.name as component,
                (SELECT bmd.value FROM binaries_metadata bmd WHERE bmd.bin_id = b.id AND bmd.key_id = :metakey_d_id) AS depends,
                (SELECT bmp.value FROM binaries_metadata bmp WHERE bmp.bin_id = b.id AND bmp.key_id = :metakey_p_id) AS provides
                FROM binaries b
                JOIN bin_associations ba ON b.id = ba.bin AND ba.suite = :suite_id
                JOIN source s ON b.source = s.id
                JOIN files_archive_map af ON b.file = af.file_id
                JOIN component c ON af.component_id = c.id
                WHERE b.architecture = :arch_id''')
        query = session.query('package', 'source', 'component', 'depends', 'provides'). \
            from_statement(statement).params(params)
        for package, source, component, depends, provides in query:
            sources[package] = source
            p2c[package] = component
            if depends is not None:
                deps[package] = depends
            # Maintain a counter for each virtual package.  If a
            # Provides: exists, set the counter to 0 and count all
            # provides by a package not in the list for removal.
            # If the counter stays 0 at the end, we know that only
            # the to-be-removed packages provided this virtual
            # package.
            if provides is not None:
                for virtual_pkg in provides.split(","):
                    virtual_pkg = virtual_pkg.strip()
                    if virtual_pkg == package:
                        continue
                    if virtual_pkg not in virtual_packages:
                        virtual_packages[virtual_pkg] = 0
                    if package not in removals:
                        virtual_packages[virtual_pkg] += 1

        # If a virtual package is only provided by the to-be-removed
        # packages, treat the virtual package as to-be-removed too.
        removal_set.update(virtual_pkg for virtual_pkg in virtual_packages if not virtual_packages[virtual_pkg])

        # Check binary dependencies (Depends)
        for package in deps:
            if package in removals:
                continue
            try:
                parsed_dep = apt_pkg.parse_depends(deps[package])
            except ValueError as e:
                print("Error for package %s: %s" % (package, e))
                parsed_dep = []
            for dep in parsed_dep:
                # Check for partial breakage.  If a package has a ORed
                # dependency, there is only a dependency problem if all
                # packages in the ORed depends will be removed.
                unsat = 0
                for dep_package, _, _ in dep:
                    if dep_package in removals:
                        unsat += 1
                if unsat == len(dep):
                    component = p2c[package]
                    source = sources[package]
                    if component != "main":
                        source = "%s/%s" % (source, component)
                    all_broken[source][package].add(architecture)
                    dep_problem = 1

    if all_broken and not quiet:
        if cruft:
            print("  - broken Depends:")
        else:
            print("# Broken Depends:")
        for source, bindict in sorted(all_broken.items()):
            lines = []
            for binary, arches in sorted(bindict.items()):
                if arches == all_arches or 'all' in arches:
                    lines.append(binary)
                else:
                    lines.append('%s [%s]' % (binary, ' '.join(sorted(arches))))
            if cruft:
                print('    %s: %s' % (source, lines[0]))
            else:
                print('%s: %s' % (source, lines[0]))
            for line in lines[1:]:
                if cruft:
                    print('    ' + ' ' * (len(source) + 2) + line)
                else:
                    print(' ' * (len(source) + 2) + line)
        if not cruft:
            print()

    # Check source dependencies (Build-Depends and Build-Depends-Indep)
    all_broken = defaultdict(set)
    metakey_bd = get_or_set_metadatakey("Build-Depends", session)
    metakey_bdi = get_or_set_metadatakey("Build-Depends-Indep", session)
    if include_arch_all:
        metakey_ids = (metakey_bd.key_id, metakey_bdi.key_id)
    else:
        metakey_ids = (metakey_bd.key_id,)

    params = {
        'suite_id':    dbsuite.suite_id,
        'metakey_ids': metakey_ids,
    }
    statement = sql.text('''
        SELECT s.source, string_agg(sm.value, ', ') as build_dep
           FROM source s
           JOIN source_metadata sm ON s.id = sm.src_id
           WHERE s.id in
               (SELECT src FROM newest_src_association
                   WHERE suite = :suite_id)
               AND sm.key_id in :metakey_ids
           GROUP BY s.id, s.source''')
    query = session.query('source', 'build_dep').from_statement(statement). \
        params(params)
    for source, build_dep in query:
        if source in removals:
            continue
        parsed_dep = []
        if build_dep is not None:
            # Remove [arch] information since we want to see breakage on all arches
            build_dep = re_build_dep_arch.sub("", build_dep)
            try:
                parsed_dep = apt_pkg.parse_src_depends(build_dep)
            except ValueError as e:
                print("Error for source %s: %s" % (source, e))
        for dep in parsed_dep:
            unsat = 0
            for dep_package, _, _ in dep:
                if dep_package in removals:
                    unsat += 1
            if unsat == len(dep):
                component, = session.query(Component.component_name) \
                    .join(Component.overrides) \
                    .filter(Override.suite == overridesuite) \
                    .filter(Override.package == re.sub('/(contrib|non-free)$', '', source)) \
                    .join(Override.overridetype).filter(OverrideType.overridetype == 'dsc') \
                    .first()
                key = source
                if component != "main":
                    key = "%s/%s" % (source, component)
                all_broken[key].add(pp_deps(dep))
                dep_problem = 1

    if all_broken and not quiet:
        if cruft:
            print("  - broken Build-Depends:")
        else:
            print("# Broken Build-Depends:")
        for source, bdeps in sorted(all_broken.items()):
            bdeps = sorted(bdeps)
            if cruft:
                print('    %s: %s' % (source, bdeps[0]))
            else:
                print('%s: %s' % (source, bdeps[0]))
            for bdep in bdeps[1:]:
                if cruft:
                    print('    ' + ' ' * (len(source) + 2) + bdep)
                else:
                    print(' ' * (len(source) + 2) + bdep)
        if not cruft:
            print()

    return dep_problem

################################################################################


def parse_built_using(control):
    """source packages referenced via Built-Using

    @type  control: dict-like
    @param control: control file to take Built-Using field from

    @rtype:  list of (str, str)
    @return: list of (source_name, source_version) pairs
    """
    built_using = control.get('Built-Using', None)
    if built_using is None:
        return []

    bu = []
    for dep in apt_pkg.parse_depends(built_using):
        assert len(dep) == 1, 'Alternatives are not allowed in Built-Using field'
        source_name, source_version, comp = dep[0]
        assert comp == '=', 'Built-Using must contain strict dependencies'
        bu.append((source_name, source_version))

    return bu

################################################################################


def is_in_debug_section(control):
    """binary package is a debug package

    @type  control: dict-like
    @param control: control file of binary package

    @rtype Boolean
    @return: True if the binary package is a debug package
    """
    section = control['Section'].split('/', 1)[-1]
    auto_built_package = control.get("Auto-Built-Package")
    return section == "debug" and auto_built_package == "debug-symbols"

################################################################################


def find_possibly_compressed_file(filename):
    """

    @type  filename: string
    @param filename: path to a control file (Sources, Packages, etc) to
                     look for

    @rtype string
    @return: path to the (possibly compressed) control file, or null if the
             file doesn't exist
    """
    _compressions = ('', '.xz', '.gz', '.bz2')

    for ext in _compressions:
        _file = filename + ext
        if os.path.exists(_file):
            return _file

    raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), filename)

################################################################################


def parse_boolean_from_user(value):
    value = value.lower()
    if value in {'yes', 'true', 'enable', 'enabled'}:
        return True
    if value in {'no', 'false', 'disable', 'disabled'}:
        return False
    raise ValueError("Not sure whether %s should be a True or a False" % value)


def suite_suffix(suite_name):
    """Return suite_suffix for the given suite"""
    suffix = Cnf.find('Dinstall::SuiteSuffix', '')
    if suffix == '':
        return ''
    elif 'Dinstall::SuiteSuffixSuites' not in Cnf:
        # TODO: warn (once per run) that SuiteSuffix will be deprecated in the future
        return suffix
    elif suite_name in Cnf.value_list('Dinstall::SuiteSuffixSuites'):
        return suffix
    return ''

################################################################################


def process_buildinfos(directory, buildinfo_files, fs_transaction, logger):
    """Copy buildinfo files into Dir::BuildinfoArchive

    @type directory: string
    @param directory: directory where .changes is stored

    @type buildinfo_files: list of str
    @param buildinfo_files: names of buildinfo files

    @type fs_transaction: L{daklib.fstransactions.FilesystemTransaction}
    @param fs_transaction: FilesystemTransaction instance

    @type logger: L{daklib.daklog.Logger}
    @param logger: logger instance
    """

    if 'Dir::BuildinfoArchive' not in Cnf:
        return

    target_dir = os.path.join(
        Cnf['Dir::BuildinfoArchive'],
        datetime.datetime.now().strftime('%Y/%m/%d'),
    )

    for f in buildinfo_files:
        src = os.path.join(directory, f.filename)
        dst = find_next_free(os.path.join(target_dir, f.filename))

        logger.log(["Archiving", f.filename])
        fs_transaction.copy(src, dst, mode=0o644)

################################################################################


def move_to_morgue(morguesubdir, filenames, fs_transaction, logger):
    """Move a file to the correct dir in morgue

    @type morguesubdir: string
    @param morguesubdir: subdirectory of morgue where this file needs to go

    @type filenames: list of str
    @param filenames: names of files

    @type fs_transaction: L{daklib.fstransactions.FilesystemTransaction}
    @param fs_transaction: FilesystemTransaction instance

    @type logger: L{daklib.daklog.Logger}
    @param logger: logger instance
    """

    morguedir = Cnf.get("Dir::Morgue", os.path.join(
        Cnf.get("Dir::Base"), 'morgue'))

    # Build directory as morguedir/morguesubdir/year/month/day
    now = datetime.datetime.now()
    dest = os.path.join(morguedir,
                        morguesubdir,
                        str(now.year),
                        '%.2d' % now.month,
                        '%.2d' % now.day)

    for filename in filenames:
        dest_filename = dest + '/' + os.path.basename(filename)
        # If the destination file exists; try to find another filename to use
        if os.path.lexists(dest_filename):
            dest_filename = find_next_free(dest_filename)
        logger.log(["move to morgue", filename, dest_filename])
        fs_transaction.move(filename, dest_filename)
