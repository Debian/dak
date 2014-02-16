#!/usr/bin/env python
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

import commands
import datetime
import email.Header
import os
import pwd
import grp
import select
import socket
import shutil
import sys
import tempfile
import traceback
import stat
import apt_inst
import apt_pkg
import time
import re
import email as modemail
import subprocess
import ldap

import daklib.config as config
import daklib.daksubprocess
from dbconn import DBConn, get_architecture, get_component, get_suite, \
                   get_override_type, Keyring, session_wrapper, \
                   get_active_keyring_paths, get_primary_keyring_path, \
                   get_suite_architectures, get_or_set_metadatakey, DBSource, \
                   Component, Override, OverrideType
from sqlalchemy import desc
from dak_exceptions import *
from gpg import SignedFile
from textutils import fix_maintainer
from regexes import re_html_escaping, html_escaping, re_single_line_field, \
                    re_multi_line_field, re_srchasver, re_taint_free, \
                    re_gpg_uid, re_re_mark, re_whitespace_comment, re_issource, \
                    re_is_orig_source, re_build_dep_arch

from formats import parse_format, validate_changes_format
from srcformats import get_format_from_string
from collections import defaultdict

################################################################################

default_config = "/etc/dak/dak.conf"     #: default dak config, defines host properties

alias_cache = None        #: Cache for email alias checks
key_uid_email_cache = {}  #: Cache for email addresses from gpg key uids

# (hashname, function, earliest_changes_version)
known_hashes = [("sha1", apt_pkg.sha1sum, (1, 8)),
                ("sha256", apt_pkg.sha256sum, (1, 8))] #: hashes we accept for entries in .changes/.dsc

# Monkeypatch commands.getstatusoutput as it may not return the correct exit
# code in lenny's Python. This also affects commands.getoutput and
# commands.getstatus.
def dak_getstatusoutput(cmd):
    pipe = daklib.daksubprocess.Popen(cmd, shell=True, universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    output = pipe.stdout.read()

    pipe.wait()

    if output[-1:] == '\n':
        output = output[:-1]

    ret = pipe.wait()
    if ret is None:
        ret = 0

    return ret, output
commands.getstatusoutput = dak_getstatusoutput

################################################################################

def html_escape(s):
    """ Escape html chars """
    return re_html_escaping.sub(lambda x: html_escaping.get(x.group(0)), s)

################################################################################

def open_file(filename, mode='r'):
    """
    Open C{file}, return fileobject.

    @type filename: string
    @param filename: path/filename to open

    @type mode: string
    @param mode: open mode

    @rtype: fileobject
    @return: open fileobject

    @raise CantOpenError: If IOError is raised by open, reraise it as CantOpenError.

    """
    try:
        f = open(filename, mode)
    except IOError:
        raise CantOpenError(filename)
    return f

################################################################################

def our_raw_input(prompt=""):
    if prompt:
        while 1:
            try:
                sys.stdout.write(prompt)
                break
            except IOError:
                pass
    sys.stdout.flush()
    try:
        ret = raw_input()
        return ret
    except EOFError:
        sys.stderr.write("\nUser interrupt (^D).\n")
        raise SystemExit

################################################################################

def extract_component_from_section(section, session=None):
    component = ""

    if section.find('/') != -1:
        component = section.split('/')[0]

    # Expand default component
    if component == "":
        comp = get_component(section, session)
        if comp is None:
            component = "main"
        else:
            component = comp.component_name

    return (section, component)

################################################################################

def parse_deb822(armored_contents, signing_rules=0, keyrings=None, session=None):
    require_signature = True
    if keyrings == None:
        keyrings = []
        require_signature = False

    signed_file = SignedFile(armored_contents, keyrings=keyrings, require_signature=require_signature)
    contents = signed_file.contents

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

    num_of_lines = len(indexed_lines.keys())
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

    if changes.has_key("source"):
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

    changes_in = open_file(filename)
    content = changes_in.read()
    changes_in.close()
    try:
        unicode(content, 'utf-8')
    except UnicodeError:
        raise ChangesUnicodeError("Changes file not proper utf-8")
    changes = parse_deb822(content, signing_rules, keyrings=keyrings)


    if not dsc_file:
        # Finally ensure that everything needed for .changes is there
        must_keywords = ('Format', 'Date', 'Source', 'Binary', 'Architecture', 'Version',
                         'Distribution', 'Maintainer', 'Description', 'Changes', 'Files')

        missingfields=[]
        for keyword in must_keywords:
            if not changes.has_key(keyword.lower()):
                missingfields.append(keyword)

                if len(missingfields):
                    raise ParseChangesError("Missing mandantory field(s) in changes file (policy 5.5): %s" % (missingfields))

    return changes

################################################################################

def hash_key(hashname):
    return '%ssum' % hashname

################################################################################

def create_hash(where, files, hashname, hashfunc):
    """
    create_hash extends the passed files dict with the given hash by
    iterating over all files on disk and passing them to the hashing
    function given.
    """

    rejmsg = []
    for f in files.keys():
        try:
            file_handle = open_file(f)
        except CantOpenError:
            rejmsg.append("Could not open file %s for checksumming" % (f))
            continue

        files[f][hash_key(hashname)] = hashfunc(file_handle)

        file_handle.close()
    return rejmsg

################################################################################

def check_hash(where, files, hashname, hashfunc):
    """
    check_hash checks the given hash in the files dict against the actual
    files on disk.  The hash values need to be present consistently in
    all file entries.  It does not modify its input in any way.
    """

    rejmsg = []
    for f in files.keys():
        file_handle = None
        try:
            try:
                file_handle = open_file(f)

                # Check for the hash entry, to not trigger a KeyError.
                if not files[f].has_key(hash_key(hashname)):
                    rejmsg.append("%s: misses %s checksum in %s" % (f, hashname,
                        where))
                    continue

                # Actually check the hash for correctness.
                if hashfunc(file_handle) != files[f][hash_key(hashname)]:
                    rejmsg.append("%s: %s check failed in %s" % (f, hashname,
                        where))
            except CantOpenError:
                # TODO: This happens when the file is in the pool.
                # warn("Cannot open file %s" % f)
                continue
        finally:
            if file_handle:
                file_handle.close()
    return rejmsg

################################################################################

def check_size(where, files):
    """
    check_size checks the file sizes in the passed files dict against the
    files on disk.
    """

    rejmsg = []
    for f in files.keys():
        try:
            entry = os.stat(f)
        except OSError as exc:
            if exc.errno == 2:
                # TODO: This happens when the file is in the pool.
                continue
            raise

        actual_size = entry[stat.ST_SIZE]
        size = int(files[f]["size"])
        if size != actual_size:
            rejmsg.append("%s: actual file size (%s) does not match size (%s) in %s"
                   % (f, actual_size, size, where))
    return rejmsg

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
        (r'orig.tar.gz',               ('orig_tar_gz', 'orig_tar')),
        (r'diff.gz',                   ('debian_diff',)),
        (r'tar.gz',                    ('native_tar_gz', 'native_tar')),
        (r'debian\.tar\.(gz|bz2|xz)',  ('debian_tar',)),
        (r'orig\.tar\.(gz|bz2|xz)',    ('orig_tar',)),
        (r'tar\.(gz|bz2|xz)',          ('native_tar',)),
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
            reject("%s: unexpected source file '%s'" % (dsc_filename, f))

    # Check for multiple files
    for file_type in ('orig_tar', 'native_tar', 'debian_tar', 'debian_diff'):
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

def check_hash_fields(what, manifest):
    """
    check_hash_fields ensures that there are no checksum fields in the
    given dict that we do not know about.
    """

    rejmsg = []
    hashes = map(lambda x: x[0], known_hashes)
    for field in manifest:
        if field.startswith("checksums-"):
            hashname = field.split("-",1)[1]
            if hashname not in hashes:
                rejmsg.append("Unsupported checksum field for %s "\
                    "in %s" % (hashname, what))
    return rejmsg

################################################################################

def _ensure_changes_hash(changes, format, version, files, hashname, hashfunc):
    if format >= version:
        # The version should contain the specified hash.
        func = check_hash

        # Import hashes from the changes
        rejmsg = parse_checksums(".changes", files, changes, hashname)
        if len(rejmsg) > 0:
            return rejmsg
    else:
        # We need to calculate the hash because it can't possibly
        # be in the file.
        func = create_hash
    return func(".changes", files, hashname, hashfunc)

# We could add the orig which might be in the pool to the files dict to
# access the checksums easily.

def _ensure_dsc_hash(dsc, dsc_files, hashname, hashfunc):
    """
    ensure_dsc_hashes' task is to ensure that each and every *present* hash
    in the dsc is correct, i.e. identical to the changes file and if necessary
    the pool.  The latter task is delegated to check_hash.
    """

    rejmsg = []
    if not dsc.has_key('Checksums-%s' % (hashname,)):
        return rejmsg
    # Import hashes from the dsc
    parse_checksums(".dsc", dsc_files, dsc, hashname)
    # And check it...
    rejmsg.extend(check_hash(".dsc", dsc_files, hashname, hashfunc))
    return rejmsg

################################################################################

def parse_checksums(where, files, manifest, hashname):
    rejmsg = []
    field = 'checksums-%s' % hashname
    if not field in manifest:
        return rejmsg
    for line in manifest[field].split('\n'):
        if not line:
            break
        clist = line.strip().split(' ')
        if len(clist) == 3:
            checksum, size, checkfile = clist
        else:
            rejmsg.append("Cannot parse checksum line [%s]" % (line))
            continue
        if not files.has_key(checkfile):
        # TODO: check for the file's entry in the original files dict, not
        # the one modified by (auto)byhand and other weird stuff
        #    rejmsg.append("%s: not present in files but in checksums-%s in %s" %
        #        (file, hashname, where))
            continue
        if not files[checkfile]["size"] == size:
            rejmsg.append("%s: size differs for files and checksums-%s entry "\
                "in %s" % (checkfile, hashname, where))
            continue
        files[checkfile][hash_key(hashname)] = checksum
    for f in files.keys():
        if not files[f].has_key(hash_key(hashname)):
            rejmsg.append("%s: no entry in checksums-%s in %s" % (f, hashname, where))
    return rejmsg

################################################################################

# Dropped support for 1.4 and ``buggy dchanges 3.4'' (?!) compared to di.pl

def build_file_list(changes, is_a_dsc=0, field="files", hashname="md5sum"):
    files = {}

    # Make sure we have a Files: field to parse...
    if not changes.has_key(field):
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

# see http://bugs.debian.org/619131
def build_package_list(dsc, session = None):
    if not dsc.has_key("package-list"):
        return {}

    packages = {}

    for line in dsc["package-list"].split("\n"):
        if not line:
            break

        fields = line.split()
        name = fields[0]
        package_type = fields[1]
        (section, component) = extract_component_from_section(fields[2])
        priority = fields[3]

        # Validate type if we have a session
        if session and get_override_type(package_type, session) is None:
            # Maybe just warn and ignore? exit(1) might be a bit hard...
            utils.fubar("invalid type (%s) in Package-List." % (package_type))

        if name not in packages or packages[name]["type"] == "dsc":
            packages[name] = dict(priority=priority, section=section, type=package_type, component=component, files=[])

    return packages

################################################################################

def send_mail (message, filename="", whitelists=None):
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
        fh = open(path, 'w')
        print >>fh, message,
        fh.close()

    # Check whether we're supposed to be sending mail
    if Cnf.has_key("Dinstall::Options::No-Mail") and Cnf["Dinstall::Options::No-Mail"]:
        return

    # If we've been passed a string dump it into a temporary file
    if message:
        (fd, filename) = tempfile.mkstemp()
        os.write (fd, message)
        os.close (fd)

    if whitelists is None or None in whitelists:
        whitelists = []
    if Cnf.get('Dinstall::MailWhiteList', ''):
        whitelists.append(Cnf['Dinstall::MailWhiteList'])
    if len(whitelists) != 0:
        message_in = open_file(filename)
        message_raw = modemail.message_from_file(message_in)
        message_in.close();

        whitelist = [];
        for path in whitelists:
          with open_file(path, 'r') as whitelist_in:
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
            if value != None:
                match = [];
                for item in value.split(","):
                    (rfc822_maint, rfc2047_maint, name, email) = fix_maintainer(item.strip())
                    mail_whitelisted = 0
                    for wr in whitelist:
                        if wr.match(email):
                            mail_whitelisted = 1
                            break
                    if not mail_whitelisted:
                        print "Skipping {0} since it's not whitelisted".format(item)
                        continue
                    match.append(item)

                # Doesn't have any mail in whitelist so remove the header
                if len(match) == 0:
                    del message_raw[field]
                else:
                    message_raw.replace_header(field, ', '.join(match))

        # Change message fields in order if we don't have a To header
        if not message_raw.has_key("To"):
            fields.reverse()
            for field in fields:
                if message_raw.has_key(field):
                    message_raw[fields[-1]] = message_raw[field]
                    del message_raw[field]
                    break
            else:
                # Clean up any temporary files
                # and return, as we removed all recipients.
                if message:
                    os.unlink (filename);
                return;

        fd = os.open(filename, os.O_RDWR|os.O_EXCL, 0o700);
        os.write (fd, message_raw.as_string(True));
        os.close (fd);

    # Invoke sendmail
    (result, output) = commands.getstatusoutput("%s < %s" % (Cnf["Dinstall::SendmailCommand"], filename))
    if (result != 0):
        raise SendmailFailedError(output)

    # Clean up any temporary files
    if message:
        os.unlink (filename)

################################################################################

def poolify (source, component=None):
    if source[:3] == "lib":
        return source[:4] + '/' + source + '/'
    else:
        return source[:1] + '/' + source + '/'

################################################################################

def move (src, dest, overwrite = 0, perms = 0o664):
    if os.path.exists(dest) and os.path.isdir(dest):
        dest_dir = dest
    else:
        dest_dir = os.path.dirname(dest)
    if not os.path.lexists(dest_dir):
        umask = os.umask(00000)
        os.makedirs(dest_dir, 0o2775)
        os.umask(umask)
    #print "Moving %s to %s..." % (src, dest)
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

def copy (src, dest, overwrite = 0, perms = 0o664):
    if os.path.exists(dest) and os.path.isdir(dest):
        dest_dir = dest
    else:
        dest_dir = os.path.dirname(dest)
    if not os.path.exists(dest_dir):
        umask = os.umask(00000)
        os.makedirs(dest_dir, 0o2775)
        os.umask(umask)
    #print "Copying %s to %s..." % (src, dest)
    if os.path.exists(dest) and os.path.isdir(dest):
        dest += '/' + os.path.basename(src)
    # Don't overwrite unless forced to
    if os.path.lexists(dest):
        if not overwrite:
            raise FileExistsError
        else:
            if not os.access(dest, os.W_OK):
                raise CantOverwriteError
    shutil.copy2(src, dest)
    os.chmod(dest, perms)

################################################################################

def which_conf_file ():
    if os.getenv('DAK_CONFIG'):
        return os.getenv('DAK_CONFIG')

    res = socket.getfqdn()
    # In case we allow local config files per user, try if one exists
    if Cnf.find_b("Config::" + res + "::AllowLocalConfig"):
        homedir = os.getenv("HOME")
        confpath = os.path.join(homedir, "/etc/dak.conf")
        if os.path.exists(confpath):
            apt_pkg.read_config_file_isc(Cnf,confpath)

    # We are still in here, so there is no local config file or we do
    # not allow local files. Do the normal stuff.
    if Cnf.get("Config::" + res + "::DakConfig"):
        return Cnf["Config::" + res + "::DakConfig"]

    return default_config

################################################################################

def TemplateSubst(subst_map, filename):
    """ Perform a substition of template """
    templatefile = open_file(filename)
    template = templatefile.read()
    for k, v in subst_map.iteritems():
        template = template.replace(k, str(v))
    templatefile.close()
    return template

################################################################################

def fubar(msg, exit_code=1):
    sys.stderr.write("E: %s\n" % (msg))
    sys.exit(exit_code)

def warn(msg):
    sys.stderr.write("W: %s\n" % (msg))

################################################################################

# Returns the user name with a laughable attempt at rfc822 conformancy
# (read: removing stray periods).
def whoami ():
    return pwd.getpwuid(os.getuid())[4].split(',')[0].replace('.', '')

def getusername ():
    return pwd.getpwuid(os.getuid())[0]

################################################################################

def size_type (c):
    t  = " B"
    if c > 10240:
        c = c / 1024
        t = " KB"
    if c > 10240:
        c = c / 1024
        t = " MB"
    return ("%d%s" % (c, t))

################################################################################

def cc_fix_changes (changes):
    o = changes.get("architecture", "")
    if o:
        del changes["architecture"]
    changes["architecture"] = {}
    for j in o.split():
        changes["architecture"][j] = 1

def changes_compare (a, b):
    """ Sort by source name, source version, 'have source', and then by filename """
    try:
        a_changes = parse_changes(a)
    except:
        return -1

    try:
        b_changes = parse_changes(b)
    except:
        return 1

    cc_fix_changes (a_changes)
    cc_fix_changes (b_changes)

    # Sort by source name
    a_source = a_changes.get("source")
    b_source = b_changes.get("source")
    q = cmp (a_source, b_source)
    if q:
        return q

    # Sort by source version
    a_version = a_changes.get("version", "0")
    b_version = b_changes.get("version", "0")
    q = apt_pkg.version_compare(a_version, b_version)
    if q:
        return q

    # Sort by 'have source'
    a_has_source = a_changes["architecture"].get("source")
    b_has_source = b_changes["architecture"].get("source")
    if a_has_source and not b_has_source:
        return -1
    elif b_has_source and not a_has_source:
        return 1

    # Fall back to sort by filename
    return cmp(a, b)

################################################################################

def find_next_free (dest, too_many=100):
    extra = 0
    orig_dest = dest
    while os.path.lexists(dest) and extra < too_many:
        dest = orig_dest + '.' + repr(extra)
        extra += 1
    if extra >= too_many:
        raise NoFreeFilenameError
    return dest

################################################################################

def result_join (original, sep = '\t'):
    resultlist = []
    for i in xrange(len(original)):
        if original[i] == None:
            resultlist.append("")
        else:
            resultlist.append(original[i])
    return sep.join(resultlist)

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

def validate_changes_file_arg(filename, require_changes=1):
    """
    'filename' is either a .changes or .dak file.  If 'filename' is a
    .dak file, it's changed to be the corresponding .changes file.  The
    function then checks if the .changes file a) exists and b) is
    readable and returns the .changes filename if so.  If there's a
    problem, the next action depends on the option 'require_changes'
    argument:

      - If 'require_changes' == -1, errors are ignored and the .changes
        filename is returned.
      - If 'require_changes' == 0, a warning is given and 'None' is returned.
      - If 'require_changes' == 1, a fatal error is raised.

    """
    error = None

    orig_filename = filename
    if filename.endswith(".dak"):
        filename = filename[:-4]+".changes"

    if not filename.endswith(".changes"):
        error = "invalid file type; not a changes file"
    else:
        if not os.access(filename,os.R_OK):
            if os.path.exists(filename):
                error = "permission denied"
            else:
                error = "file not found"

    if error:
        if require_changes == 1:
            fubar("%s: %s." % (orig_filename, error))
        elif require_changes == 0:
            warn("Skipping %s - %s" % (orig_filename, error))
            return None
        else: # We only care about the .dak file
            return filename
    else:
        return filename

################################################################################

def real_arch(arch):
    return (arch != "source" and arch != "all")

################################################################################

def join_with_commas_and(list):
    if len(list) == 0: return "nothing"
    if len(list) == 1: return list[0]
    return ", ".join(list[:-1]) + " and " + list[-1]

################################################################################

def pp_deps (deps):
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
            con_suites = "AND su.id IN (%s)" % ", ".join([ str(i) for i in suite_ids_list ])
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
            con_components = "AND c.id IN (%s)" % ", ".join([ str(i) for i in component_ids_list ])
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
            con_architectures = "AND a.id IN (%s)" % ", ".join([ str(i) for i in arch_ids_list ])
        else:
            if not check_source:
                fubar("No valid architecture given.")
    else:
        check_source = 1

    return (con_suites, con_architectures, con_components, check_source)

################################################################################

def arch_compare_sw (a, b):
    """
    Function for use in sorting lists of architectures.

    Sorts normally except that 'source' dominates all others.
    """

    if a == "source" and b == "source":
        return 0
    elif a == "source":
        return -1
    elif b == "source":
        return 1

    return cmp (a, b)

################################################################################

def split_args (s, dwim=1):
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

def gpgv_get_status_output(cmd, status_read, status_write):
    """
    Our very own version of commands.getouputstatus(), hacked to support
    gpgv's status fd.
    """

    cmd = ['/bin/sh', '-c', cmd]
    p2cread, p2cwrite = os.pipe()
    c2pread, c2pwrite = os.pipe()
    errout, errin = os.pipe()
    pid = os.fork()
    if pid == 0:
        # Child
        os.close(0)
        os.close(1)
        os.dup(p2cread)
        os.dup(c2pwrite)
        os.close(2)
        os.dup(errin)
        for i in range(3, 256):
            if i != status_write:
                try:
                    os.close(i)
                except:
                    pass
        try:
            os.execvp(cmd[0], cmd)
        finally:
            os._exit(1)

    # Parent
    os.close(p2cread)
    os.dup2(c2pread, c2pwrite)
    os.dup2(errout, errin)

    output = status = ""
    while 1:
        i, o, e = select.select([c2pwrite, errin, status_read], [], [])
        more_data = []
        for fd in i:
            r = os.read(fd, 8196)
            if len(r) > 0:
                more_data.append(fd)
                if fd == c2pwrite or fd == errin:
                    output += r
                elif fd == status_read:
                    status += r
                else:
                    fubar("Unexpected file descriptor [%s] returned from select\n" % (fd))
        if not more_data:
            pid, exit_status = os.waitpid(pid, 0)
            try:
                os.close(status_write)
                os.close(status_read)
                os.close(c2pread)
                os.close(c2pwrite)
                os.close(p2cwrite)
                os.close(errin)
                os.close(errout)
            except:
                pass
            break

    return output, status, exit_status

################################################################################

def process_gpgv_output(status):
    # Process the status-fd output
    keywords = {}
    internal_error = ""
    for line in status.split('\n'):
        line = line.strip()
        if line == "":
            continue
        split = line.split()
        if len(split) < 2:
            internal_error += "gpgv status line is malformed (< 2 atoms) ['%s'].\n" % (line)
            continue
        (gnupg, keyword) = split[:2]
        if gnupg != "[GNUPG:]":
            internal_error += "gpgv status line is malformed (incorrect prefix '%s').\n" % (gnupg)
            continue
        args = split[2:]
        if keywords.has_key(keyword) and keyword not in [ "NODATA", "SIGEXPIRED", "KEYEXPIRED" ]:
            internal_error += "found duplicate status token ('%s').\n" % (keyword)
            continue
        else:
            keywords[keyword] = args

    return (keywords, internal_error)

################################################################################

def retrieve_key (filename, keyserver=None, keyring=None):
    """
    Retrieve the key that signed 'filename' from 'keyserver' and
    add it to 'keyring'.  Returns nothing on success, or an error message
    on error.
    """

    # Defaults for keyserver and keyring
    if not keyserver:
        keyserver = Cnf["Dinstall::KeyServer"]
    if not keyring:
        keyring = get_primary_keyring_path()

    # Ensure the filename contains no shell meta-characters or other badness
    if not re_taint_free.match(filename):
        return "%s: tainted filename" % (filename)

    # Invoke gpgv on the file
    status_read, status_write = os.pipe()
    cmd = "gpgv --status-fd %s --keyring /dev/null %s" % (status_write, filename)
    (_, status, _) = gpgv_get_status_output(cmd, status_read, status_write)

    # Process the status-fd output
    (keywords, internal_error) = process_gpgv_output(status)
    if internal_error:
        return internal_error

    if not keywords.has_key("NO_PUBKEY"):
        return "didn't find expected NO_PUBKEY in gpgv status-fd output"

    fingerprint = keywords["NO_PUBKEY"][0]
    # XXX - gpg sucks.  You can't use --secret-keyring=/dev/null as
    # it'll try to create a lockfile in /dev.  A better solution might
    # be a tempfile or something.
    cmd = "gpg --no-default-keyring --secret-keyring=%s --no-options" \
          % (Cnf["Dinstall::SigningKeyring"])
    cmd += " --keyring %s --keyserver %s --recv-key %s" \
           % (keyring, keyserver, fingerprint)
    (result, output) = commands.getstatusoutput(cmd)
    if (result != 0):
        return "'%s' failed with exit code %s" % (cmd, result)

    return ""

################################################################################

def gpg_keyring_args(keyrings=None):
    if not keyrings:
        keyrings = get_active_keyring_paths()

    return " ".join(["--keyring %s" % x for x in keyrings])

################################################################################
@session_wrapper
def check_signature (sig_filename, data_filename="", keyrings=None, autofetch=None, session=None):
    """
    Check the signature of a file and return the fingerprint if the
    signature is valid or 'None' if it's not.  The first argument is the
    filename whose signature should be checked.  The second argument is a
    reject function and is called when an error is found.  The reject()
    function must allow for two arguments: the first is the error message,
    the second is an optional prefix string.  It's possible for reject()
    to be called more than once during an invocation of check_signature().
    The third argument is optional and is the name of the files the
    detached signature applies to.  The fourth argument is optional and is
    a *list* of keyrings to use.  'autofetch' can either be None, True or
    False.  If None, the default behaviour specified in the config will be
    used.
    """

    rejects = []

    # Ensure the filename contains no shell meta-characters or other badness
    if not re_taint_free.match(sig_filename):
        rejects.append("!!WARNING!! tainted signature filename: '%s'." % (sig_filename))
        return (None, rejects)

    if data_filename and not re_taint_free.match(data_filename):
        rejects.append("!!WARNING!! tainted data filename: '%s'." % (data_filename))
        return (None, rejects)

    if not keyrings:
        keyrings = [ x.keyring_name for x in session.query(Keyring).filter(Keyring.active == True).all() ]

    # Autofetch the signing key if that's enabled
    if autofetch == None:
        autofetch = Cnf.get("Dinstall::KeyAutoFetch")
    if autofetch:
        error_msg = retrieve_key(sig_filename)
        if error_msg:
            rejects.append(error_msg)
            return (None, rejects)

    # Build the command line
    status_read, status_write = os.pipe()
    cmd = "gpgv --status-fd %s %s %s %s" % (
        status_write, gpg_keyring_args(keyrings), sig_filename, data_filename)

    # Invoke gpgv on the file
    (output, status, exit_status) = gpgv_get_status_output(cmd, status_read, status_write)

    # Process the status-fd output
    (keywords, internal_error) = process_gpgv_output(status)

    # If we failed to parse the status-fd output, let's just whine and bail now
    if internal_error:
        rejects.append("internal error while performing signature check on %s." % (sig_filename))
        rejects.append(internal_error, "")
        rejects.append("Please report the above errors to the Archive maintainers by replying to this mail.", "")
        return (None, rejects)

    # Now check for obviously bad things in the processed output
    if keywords.has_key("KEYREVOKED"):
        rejects.append("The key used to sign %s has been revoked." % (sig_filename))
    if keywords.has_key("BADSIG"):
        rejects.append("bad signature on %s." % (sig_filename))
    if keywords.has_key("ERRSIG") and not keywords.has_key("NO_PUBKEY"):
        rejects.append("failed to check signature on %s." % (sig_filename))
    if keywords.has_key("NO_PUBKEY"):
        args = keywords["NO_PUBKEY"]
        if len(args) >= 1:
            key = args[0]
        rejects.append("The key (0x%s) used to sign %s wasn't found in the keyring(s)." % (key, sig_filename))
    if keywords.has_key("BADARMOR"):
        rejects.append("ASCII armour of signature was corrupt in %s." % (sig_filename))
    if keywords.has_key("NODATA"):
        rejects.append("no signature found in %s." % (sig_filename))
    if keywords.has_key("EXPKEYSIG"):
        args = keywords["EXPKEYSIG"]
        if len(args) >= 1:
            key = args[0]
        rejects.append("Signature made by expired key 0x%s" % (key))
    if keywords.has_key("KEYEXPIRED") and not keywords.has_key("GOODSIG"):
        args = keywords["KEYEXPIRED"]
        expiredate=""
        if len(args) >= 1:
            timestamp = args[0]
            if timestamp.count("T") == 0:
                try:
                    expiredate = time.strftime("%Y-%m-%d", time.gmtime(float(timestamp)))
                except ValueError:
                    expiredate = "unknown (%s)" % (timestamp)
            else:
                expiredate = timestamp
        rejects.append("The key used to sign %s has expired on %s" % (sig_filename, expiredate))

    if len(rejects) > 0:
        return (None, rejects)

    # Next check gpgv exited with a zero return code
    if exit_status:
        rejects.append("gpgv failed while checking %s." % (sig_filename))
        if status.strip():
            rejects.append(prefix_multi_line_string(status, " [GPG status-fd output:] "))
        else:
            rejects.append(prefix_multi_line_string(output, " [GPG output:] "))
        return (None, rejects)

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        rejects.append("signature on %s does not appear to be valid [No VALIDSIG]." % (sig_filename))
    else:
        args = keywords["VALIDSIG"]
        if len(args) < 1:
            rejects.append("internal error while checking signature on %s." % (sig_filename))
        else:
            fingerprint = args[0]
    if not keywords.has_key("GOODSIG"):
        rejects.append("signature on %s does not appear to be valid [No GOODSIG]." % (sig_filename))
    if not keywords.has_key("SIG_ID"):
        rejects.append("signature on %s does not appear to be valid [No SIG_ID]." % (sig_filename))

    # Finally ensure there's not something we don't recognise
    known_keywords = dict(VALIDSIG="",SIG_ID="",GOODSIG="",BADSIG="",ERRSIG="",
                          SIGEXPIRED="",KEYREVOKED="",NO_PUBKEY="",BADARMOR="",
                          NODATA="",NOTATION_DATA="",NOTATION_NAME="",KEYEXPIRED="",POLICY_URL="")

    for keyword in keywords.keys():
        if not known_keywords.has_key(keyword):
            rejects.append("found unknown status token '%s' from gpgv with args '%r' in %s." % (keyword, keywords[keyword], sig_filename))

    if len(rejects) > 0:
        return (None, rejects)
    else:
        return (fingerprint, [])

################################################################################

def gpg_get_key_addresses(fingerprint):
    """retreive email addresses from gpg key uids for a given fingerprint"""
    addresses = key_uid_email_cache.get(fingerprint)
    if addresses != None:
        return addresses
    addresses = list()
    cmd = "gpg --no-default-keyring %s --fingerprint %s" \
                % (gpg_keyring_args(), fingerprint)
    (result, output) = commands.getstatusoutput(cmd)
    if result == 0:
        for l in output.split('\n'):
            m = re_gpg_uid.match(l)
            if not m:
                continue
            address = m.group(1)
            if address.endswith('@debian.org'):
                # prefer @debian.org addresses
                # TODO: maybe not hardcode the domain
                addresses.insert(0, address)
            else:
                addresses.append(m.group(1))
    key_uid_email_cache[fingerprint] = addresses
    return addresses

################################################################################

def get_logins_from_ldap(fingerprint='*'):
    """retrieve login from LDAP linked to a given fingerprint"""

    LDAPDn = Cnf['Import-LDAP-Fingerprints::LDAPDn']
    LDAPServer = Cnf['Import-LDAP-Fingerprints::LDAPServer']
    l = ldap.open(LDAPServer)
    l.simple_bind_s('','')
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       '(keyfingerprint=%s)' % fingerprint,
                       ['uid', 'keyfingerprint'])
    login = {}
    for elem in Attrs:
        login[elem[1]['keyFingerPrint'][0]] = elem[1]['uid'][0]
    return login

################################################################################

def get_users_from_ldap():
    """retrieve login and user names from LDAP"""

    LDAPDn = Cnf['Import-LDAP-Fingerprints::LDAPDn']
    LDAPServer = Cnf['Import-LDAP-Fingerprints::LDAPServer']
    l = ldap.open(LDAPServer)
    l.simple_bind_s('','')
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       '(uid=*)', ['uid', 'cn', 'mn', 'sn'])
    users = {}
    for elem in Attrs:
        elem = elem[1]
        name = []
        for k in ('cn', 'mn', 'sn'):
            try:
                if elem[k][0] != '-':
                    name.append(elem[k][0])
            except KeyError:
                pass
        users[' '.join(name)] = elem['uid'][0]
    return users

################################################################################

def clean_symlink (src, dest, root):
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

def temp_filename(directory=None, prefix="dak", suffix="", mode=None, group=None):
    """
    Return a secure and unique filename by pre-creating it.

    @type directory: str
    @param directory: If non-null it will be the directory the file is pre-created in.

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

    (tfd, tfname) = tempfile.mkstemp(suffix, prefix, directory)
    if mode:
        os.chmod(tfname, mode)
    if group:
        gid = grp.getgrnam(group).gr_gid
        os.chown(tfname, -1, gid)
    return (tfd, tfname)

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

def is_email_alias(email):
    """ checks if the user part of the email is listed in the alias file """
    global alias_cache
    if alias_cache == None:
        aliasfn = which_alias_file()
        alias_cache = set()
        if aliasfn:
            for l in open(aliasfn):
                alias_cache.add(l.split(':')[0])
    uid = email.split('@')[0]
    return uid in alias_cache

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

def parse_wnpp_bug_file(file = "/srv/ftp-master.debian.org/scripts/masterfiles/wnpp_rm"):
    """
    Parses the wnpp bug list available at http://qa.debian.org/data/bts/wnpp_rm
    Well, actually it parsed a local copy, but let's document the source
    somewhere ;)

    returns a dict associating source package name with a list of open wnpp
    bugs (Yes, there might be more than one)
    """

    line = []
    try:
        f = open(file)
        lines = f.readlines()
    except IOError as e:
        print "Warning:  Couldn't open %s; don't know about WNPP bugs, so won't close any." % file
	lines = []
    wnpp = {}

    for line in lines:
        splited_line = line.split(": ", 1)
        if len(splited_line) > 1:
            wnpp[splited_line[0]] = splited_line[1].split("|")

    for source in wnpp.keys():
        bugs = []
        for wnpp_bug in wnpp[source]:
            bug_no = re.search("(\d)+", wnpp_bug).group()
            if bug_no:
                bugs.append(bug_no)
        wnpp[source] = bugs
    return wnpp

################################################################################

def get_packages_from_ftp(root, suite, component, architecture):
    """
    Returns an object containing apt_pkg-parseable data collected by
    aggregating Packages.gz files gathered for each architecture.

    @type root: string
    @param root: path to ftp archive root directory

    @type suite: string
    @param suite: suite to extract files from

    @type component: string
    @param component: component to extract files from

    @type architecture: string
    @param architecture: architecture to extract files from

    @rtype: TagFile
    @return: apt_pkg class containing package data
    """
    filename = "%s/dists/%s/%s/binary-%s/Packages.gz" % (root, suite, component, architecture)
    (fd, temp_file) = temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_file))
    if (result != 0):
        fubar("Gunzip invocation failed!\n%s\n" % (output), result)
    filename = "%s/dists/%s/%s/debian-installer/binary-%s/Packages.gz" % (root, suite, component, architecture)
    if os.path.exists(filename):
        (result, output) = commands.getstatusoutput("gunzip -c %s >> %s" % (filename, temp_file))
        if (result != 0):
            fubar("Gunzip invocation failed!\n%s\n" % (output), result)
    packages = open_file(temp_file)
    Packages = apt_pkg.TagFile(packages)
    os.unlink(temp_file)
    return Packages

################################################################################

def deb_extract_control(fh):
    """extract DEBIAN/control from a binary package"""
    return apt_inst.DebFile(fh).control.extractdata("control")

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
    addresses = [maintainer]
    if changed_by != maintainer:
        addresses.append(changed_by)

    fpr_addresses = gpg_get_key_addresses(fingerprint)
    if len(fpr_addresses) > 0 and fix_maintainer(changed_by)[3] not in fpr_addresses and fix_maintainer(maintainer)[3] not in fpr_addresses:
        addresses.append(fpr_addresses[0])

    encoded_addresses = [ fix_maintainer(e)[1] for e in addresses ]
    return encoded_addresses

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
    editor = os.environ.get('VISUAL', os.environ.get('EDITOR', 'vi'))
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        print >>tmp, text,
        tmp.close()
        daklib.daksubprocess.check_call([editor, tmp.name])
        return open(tmp.name, 'r').read()
    finally:
        os.unlink(tmp.name)

################################################################################

def check_reverse_depends(removals, suite, arches=None, session=None, cruft=False):
    dbsuite = get_suite(suite, session)
    overridesuite = dbsuite
    if dbsuite.overridesuite is not None:
        overridesuite = get_suite(dbsuite.overridesuite, session)
    dep_problem = 0
    p2c = {}
    all_broken = {}
    if arches:
        all_arches = set(arches)
    else:
        all_arches = set([x.arch_string for x in get_suite_architectures(suite)])
    all_arches -= set(["source", "all"])
    metakey_d = get_or_set_metadatakey("Depends", session)
    metakey_p = get_or_set_metadatakey("Provides", session)
    params = {
        'suite_id':     dbsuite.suite_id,
        'metakey_d_id': metakey_d.key_id,
        'metakey_p_id': metakey_p.key_id,
    }
    for architecture in all_arches | set(['all']):
        deps = {}
        sources = {}
        virtual_packages = {}
        params['arch_id'] = get_architecture(architecture, session).arch_id

        statement = '''
            SELECT b.id, b.package, s.source, c.name as component,
                (SELECT bmd.value FROM binaries_metadata bmd WHERE bmd.bin_id = b.id AND bmd.key_id = :metakey_d_id) AS depends,
                (SELECT bmp.value FROM binaries_metadata bmp WHERE bmp.bin_id = b.id AND bmp.key_id = :metakey_p_id) AS provides
                FROM binaries b
                JOIN bin_associations ba ON b.id = ba.bin AND ba.suite = :suite_id
                JOIN source s ON b.source = s.id
                JOIN files_archive_map af ON b.file = af.file_id
                JOIN component c ON af.component_id = c.id
                WHERE b.architecture = :arch_id'''
        query = session.query('id', 'package', 'source', 'component', 'depends', 'provides'). \
            from_statement(statement).params(params)
        for binary_id, package, source, component, depends, provides in query:
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
                    if virtual_pkg == package: continue
                    if not virtual_packages.has_key(virtual_pkg):
                        virtual_packages[virtual_pkg] = 0
                    if package not in removals:
                        virtual_packages[virtual_pkg] += 1

        # If a virtual package is only provided by the to-be-removed
        # packages, treat the virtual package as to-be-removed too.
        for virtual_pkg in virtual_packages.keys():
            if virtual_packages[virtual_pkg] == 0:
                removals.append(virtual_pkg)

        # Check binary dependencies (Depends)
        for package in deps.keys():
            if package in removals: continue
            parsed_dep = []
            try:
                parsed_dep += apt_pkg.parse_depends(deps[package])
            except ValueError as e:
                print "Error for package %s: %s" % (package, e)
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
                    all_broken.setdefault(source, {}).setdefault(package, set()).add(architecture)
                    dep_problem = 1

    if all_broken:
        if cruft:
            print "  - broken Depends:"
        else:
            print "# Broken Depends:"
        for source, bindict in sorted(all_broken.items()):
            lines = []
            for binary, arches in sorted(bindict.items()):
                if arches == all_arches or 'all' in arches:
                    lines.append(binary)
                else:
                    lines.append('%s [%s]' % (binary, ' '.join(sorted(arches))))
            if cruft:
                print '    %s: %s' % (source, lines[0])
            else:
                print '%s: %s' % (source, lines[0])
            for line in lines[1:]:
                if cruft:
                    print '    ' + ' ' * (len(source) + 2) + line
                else:
                    print ' ' * (len(source) + 2) + line
        if not cruft:
            print

    # Check source dependencies (Build-Depends and Build-Depends-Indep)
    all_broken.clear()
    metakey_bd = get_or_set_metadatakey("Build-Depends", session)
    metakey_bdi = get_or_set_metadatakey("Build-Depends-Indep", session)
    params = {
        'suite_id':    dbsuite.suite_id,
        'metakey_ids': (metakey_bd.key_id, metakey_bdi.key_id),
    }
    statement = '''
        SELECT s.id, s.source, string_agg(sm.value, ', ') as build_dep
           FROM source s
           JOIN source_metadata sm ON s.id = sm.src_id
           WHERE s.id in
               (SELECT source FROM src_associations
                   WHERE suite = :suite_id)
               AND sm.key_id in :metakey_ids
           GROUP BY s.id, s.source'''
    query = session.query('id', 'source', 'build_dep').from_statement(statement). \
        params(params)
    for source_id, source, build_dep in query:
        if source in removals: continue
        parsed_dep = []
        if build_dep is not None:
            # Remove [arch] information since we want to see breakage on all arches
            build_dep = re_build_dep_arch.sub("", build_dep)
            try:
                parsed_dep += apt_pkg.parse_depends(build_dep)
            except ValueError as e:
                print "Error for source %s: %s" % (source, e)
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
                all_broken.setdefault(key, set()).add(pp_deps(dep))
                dep_problem = 1

    if all_broken:
        if cruft:
            print "  - broken Build-Depends:"
        else:
            print "# Broken Build-Depends:"
        for source, bdeps in sorted(all_broken.items()):
            bdeps = sorted(bdeps)
            if cruft:
                print '    %s: %s' % (source, bdeps[0])
            else:
                print '%s: %s' % (source, bdeps[0])
            for bdep in bdeps[1:]:
                if cruft:
                    print '    ' + ' ' * (len(source) + 2) + bdep
                else:
                    print ' ' * (len(source) + 2) + bdep
        if not cruft:
            print

    return dep_problem
