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

import codecs
import commands
import email.Header
import os
import pwd
import select
import socket
import shutil
import sys
import tempfile
import traceback
import stat
import apt_pkg
import database
import time
import re
import string
import email as modemail
from dak_exceptions import *
from regexes import re_html_escaping, html_escaping, re_single_line_field, \
                    re_multi_line_field, re_srchasver, re_verwithext, \
                    re_parse_maintainer, re_taint_free, re_gpg_uid, re_re_mark, \
                    re_whitespace_comment

################################################################################

#default_config = "/etc/dak/dak.conf"     #: default dak config, defines host properties
default_config = "/home/stew/etc/dak/dak.conf"     #: default dak config, defines host properties
default_apt_config = "/etc/dak/apt.conf" #: default apt config, not normally used

alias_cache = None        #: Cache for email alias checks
key_uid_email_cache = {}  #: Cache for email addresses from gpg key uids

# (hashname, function, earliest_changes_version)
known_hashes = [("sha1", apt_pkg.sha1sum, (1, 8)),
                ("sha256", apt_pkg.sha256sum, (1, 8))] #: hashes we accept for entries in .changes/.dsc

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
        raise CantOpenError, filename
    return f

################################################################################

def our_raw_input(prompt=""):
    if prompt:
        sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        ret = raw_input()
        return ret
    except EOFError:
        sys.stderr.write("\nUser interrupt (^D).\n")
        raise SystemExit

################################################################################

def extract_component_from_section(section):
    component = ""

    if section.find('/') != -1:
        component = section.split('/')[0]

    # Expand default component
    if component == "":
        if Cnf.has_key("Component::%s" % section):
            component = section
        else:
            component = "main"

    return (section, component)

################################################################################

def parse_deb822(contents, signing_rules=0):
    error = ""
    changes = {}

    # Split the lines in the input, keeping the linebreaks.
    lines = contents.splitlines(True)

    if len(lines) == 0:
        raise ParseChangesError, "[Empty changes file]"

    # Reindex by line number so we can easily verify the format of
    # .dsc files...
    index = 0
    indexed_lines = {}
    for line in lines:
        index += 1
        indexed_lines[index] = line[:-1]

    inside_signature = 0

    num_of_lines = len(indexed_lines.keys())
    index = 0
    first = -1
    while index < num_of_lines:
        index += 1
        line = indexed_lines[index]
        if line == "":
            if signing_rules == 1:
                index += 1
                if index > num_of_lines:
                    raise InvalidDscError, index
                line = indexed_lines[index]
                if not line.startswith("-----BEGIN PGP SIGNATURE"):
                    raise InvalidDscError, index
                inside_signature = 0
                break
            else:
                continue
        if line.startswith("-----BEGIN PGP SIGNATURE"):
            break
        if line.startswith("-----BEGIN PGP SIGNED MESSAGE"):
            inside_signature = 1
            if signing_rules == 1:
                while index < num_of_lines and line != "":
                    index += 1
                    line = indexed_lines[index]
            continue
        # If we're not inside the signed data, don't process anything
        if signing_rules >= 0 and not inside_signature:
            continue
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
                raise ParseChangesError, "'%s'\n [Multi-line field continuing on from nothing?]" % (line)
            if first == 1 and changes[field] != "":
                changes[field] += '\n'
            first = 0
            changes[field] += mlf.groups()[0] + '\n'
            continue
        error += line

    if signing_rules == 1 and inside_signature:
        raise InvalidDscError, index

    changes["filecontents"] = "".join(lines)

    if changes.has_key("source"):
        # Strip the source version in brackets from the source field,
        # put it in the "source-version" field instead.
        srcver = re_srchasver.search(changes["source"])
        if srcver:
            changes["source"] = srcver.group(1)
            changes["source-version"] = srcver.group(2)

    if error:
        raise ParseChangesError, error

    return changes

################################################################################

def parse_changes(filename, signing_rules=0):
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
        raise ChangesUnicodeError, "Changes file not proper utf-8"
    return parse_deb822(content, signing_rules)

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
        except OSError, exc:
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

def ensure_hashes(changes, dsc, files, dsc_files):
    rejmsg = []

    # Make sure we recognise the format of the Files: field in the .changes
    format = changes.get("format", "0.0").split(".", 1)
    if len(format) == 2:
        format = int(format[0]), int(format[1])
    else:
        format = int(float(format[0])), 0

    # We need to deal with the original changes blob, as the fields we need
    # might not be in the changes dict serialised into the .dak anymore.
    orig_changes = parse_deb822(changes['filecontents'])

    # Copy the checksums over to the current changes dict.  This will keep
    # the existing modifications to it intact.
    for field in orig_changes:
        if field.startswith('checksums-'):
            changes[field] = orig_changes[field]

    # Check for unsupported hashes
    rejmsg.extend(check_hash_fields(".changes", changes))
    rejmsg.extend(check_hash_fields(".dsc", dsc))

    # We have to calculate the hash if we have an earlier changes version than
    # the hash appears in rather than require it exist in the changes file
    for hashname, hashfunc, version in known_hashes:
        rejmsg.extend(_ensure_changes_hash(changes, format, version, files,
            hashname, hashfunc))
        if "source" in changes["architecture"]:
            rejmsg.extend(_ensure_dsc_hash(dsc, dsc_files, hashname,
                hashfunc))

    return rejmsg

def parse_checksums(where, files, manifest, hashname):
    rejmsg = []
    field = 'checksums-%s' % hashname
    if not field in manifest:
        return rejmsg
    for line in manifest[field].split('\n'):
        if not line:
            break
        checksum, size, checkfile = line.strip().split(' ')
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
            rejmsg.append("%s: no entry in checksums-%s in %s" % (checkfile,
                hashname, where))
    return rejmsg

################################################################################

# Dropped support for 1.4 and ``buggy dchanges 3.4'' (?!) compared to di.pl

def build_file_list(changes, is_a_dsc=0, field="files", hashname="md5sum"):
    files = {}

    # Make sure we have a Files: field to parse...
    if not changes.has_key(field):
        raise NoFilesFieldError

    # Make sure we recognise the format of the Files: field
    format = re_verwithext.search(changes.get("format", "0.0"))
    if not format:
        raise UnknownFormatError, "%s" % (changes.get("format","0.0"))

    format = format.groups()
    if format[1] == None:
        format = int(float(format[0])), 0, format[2]
    else:
        format = int(format[0]), int(format[1]), format[2]
    if format[2] == None:
        format = format[:2]

    if is_a_dsc:
        # format = (1,0) are the only formats we currently accept,
        # format = (0,0) are missing format headers of which we still
        # have some in the archive.
        if format != (1,0) and format != (0,0):
            raise UnknownFormatError, "%s" % (changes.get("format","0.0"))
    else:
        if (format < (1,5) or format > (1,8)):
            raise UnknownFormatError, "%s" % (changes.get("format","0.0"))
        if field != "files" and format < (1,8):
            raise UnknownFormatError, "%s" % (changes.get("format","0.0"))

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
            raise ParseChangesError, i

        if section == "":
            section = "-"
        if priority == "":
            priority = "-"

        (section, component) = extract_component_from_section(section)

        files[name] = Dict(size=size, section=section,
                           priority=priority, component=component)
        files[name][hashname] = md5

    return files

################################################################################

def force_to_utf8(s):
    """
    Forces a string to UTF-8.  If the string isn't already UTF-8,
    it's assumed to be ISO-8859-1.
    """
    try:
        unicode(s, 'utf-8')
        return s
    except UnicodeError:
        latin1_s = unicode(s,'iso8859-1')
        return latin1_s.encode('utf-8')

def rfc2047_encode(s):
    """
    Encodes a (header) string per RFC2047 if necessary.  If the
    string is neither ASCII nor UTF-8, it's assumed to be ISO-8859-1.
    """
    try:
        codecs.lookup('ascii')[1](s)
        return s
    except UnicodeError:
        pass
    try:
        codecs.lookup('utf-8')[1](s)
        h = email.Header.Header(s, 'utf-8', 998)
        return str(h)
    except UnicodeError:
        h = email.Header.Header(s, 'iso-8859-1', 998)
        return str(h)

################################################################################

# <Culus> 'The standard sucks, but my tool is supposed to interoperate
#          with it. I know - I'll fix the suckage and make things
#          incompatible!'

def fix_maintainer (maintainer):
    """
    Parses a Maintainer or Changed-By field and returns:
      1. an RFC822 compatible version,
      2. an RFC2047 compatible version,
      3. the name
      4. the email

    The name is forced to UTF-8 for both 1. and 3..  If the name field
    contains '.' or ',' (as allowed by Debian policy), 1. and 2. are
    switched to 'email (name)' format.

    """
    maintainer = maintainer.strip()
    if not maintainer:
        return ('', '', '', '')

    if maintainer.find("<") == -1:
        email = maintainer
        name = ""
    elif (maintainer[0] == "<" and maintainer[-1:] == ">"):
        email = maintainer[1:-1]
        name = ""
    else:
        m = re_parse_maintainer.match(maintainer)
        if not m:
            raise ParseMaintError, "Doesn't parse as a valid Maintainer field."
        name = m.group(1)
        email = m.group(2)

    # Get an RFC2047 compliant version of the name
    rfc2047_name = rfc2047_encode(name)

    # Force the name to be UTF-8
    name = force_to_utf8(name)

    if name.find(',') != -1 or name.find('.') != -1:
        rfc822_maint = "%s (%s)" % (email, name)
        rfc2047_maint = "%s (%s)" % (email, rfc2047_name)
    else:
        rfc822_maint = "%s <%s>" % (name, email)
        rfc2047_maint = "%s <%s>" % (rfc2047_name, email)

    if email.find("@") == -1 and email.find("buildd_") != 0:
        raise ParseMaintError, "No @ found in email address part."

    return (rfc822_maint, rfc2047_maint, name, email)

################################################################################

def send_mail (message, filename=""):
    """sendmail wrapper, takes _either_ a message string or a file as arguments"""

    # If we've been passed a string dump it into a temporary file
    if message:
        (fd, filename) = tempfile.mkstemp()
        os.write (fd, message)
        os.close (fd)

    if Cnf.has_key("Dinstall::MailWhiteList") and \
           Cnf["Dinstall::MailWhiteList"] != "":
        message_in = open_file(filename)
        message_raw = modemail.message_from_file(message_in)
        message_in.close();

        whitelist = [];
        whitelist_in = open_file(Cnf["Dinstall::MailWhiteList"])
        try:
            for line in whitelist_in:
                if not re_whitespace_comment.match(line):
                    if re_re_mark.match(line):
                        whitelist.append(re.compile(re_re_mark.sub("", line.strip(), 1)))
                    else:
                        whitelist.append(re.compile(re.escape(line.strip())))
        finally:
            whitelist_in.close()

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
                        print "Skipping %s since it's not in %s" % (item, Cnf["Dinstall::MailWhiteList"])
                        continue
                    match.append(item)

                # Doesn't have any mail in whitelist so remove the header
                if len(match) == 0:
                    del message_raw[field]
                else:
                    message_raw.replace_header(field, string.join(match, ", "))

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

        fd = os.open(filename, os.O_RDWR|os.O_EXCL, 0700);
        os.write (fd, message_raw.as_string(True));
        os.close (fd);

    # Invoke sendmail
    (result, output) = commands.getstatusoutput("%s < %s" % (Cnf["Dinstall::SendmailCommand"], filename))
    if (result != 0):
        raise SendmailFailedError, output

    # Clean up any temporary files
    if message:
        os.unlink (filename)

################################################################################

def poolify (source, component):
    if component:
        component += '/'
    if source[:3] == "lib":
        return component + source[:4] + '/' + source + '/'
    else:
        return component + source[:1] + '/' + source + '/'

################################################################################

def move (src, dest, overwrite = 0, perms = 0664):
    if os.path.exists(dest) and os.path.isdir(dest):
        dest_dir = dest
    else:
        dest_dir = os.path.dirname(dest)
    if not os.path.exists(dest_dir):
        umask = os.umask(00000)
        os.makedirs(dest_dir, 02775)
        os.umask(umask)
    #print "Moving %s to %s..." % (src, dest)
    if os.path.exists(dest) and os.path.isdir(dest):
        dest += '/' + os.path.basename(src)
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            fubar("Can't move %s to %s - file already exists." % (src, dest))
        else:
            if not os.access(dest, os.W_OK):
                fubar("Can't move %s to %s - can't write to existing file." % (src, dest))
    shutil.copy2(src, dest)
    os.chmod(dest, perms)
    os.unlink(src)

def copy (src, dest, overwrite = 0, perms = 0664):
    if os.path.exists(dest) and os.path.isdir(dest):
        dest_dir = dest
    else:
        dest_dir = os.path.dirname(dest)
    if not os.path.exists(dest_dir):
        umask = os.umask(00000)
        os.makedirs(dest_dir, 02775)
        os.umask(umask)
    #print "Copying %s to %s..." % (src, dest)
    if os.path.exists(dest) and os.path.isdir(dest):
        dest += '/' + os.path.basename(src)
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            raise FileExistsError
        else:
            if not os.access(dest, os.W_OK):
                raise CantOverwriteError
    shutil.copy2(src, dest)
    os.chmod(dest, perms)

################################################################################

def where_am_i ():
    res = socket.gethostbyaddr(socket.gethostname())
    database_hostname = Cnf.get("Config::" + res[0] + "::DatabaseHostname")
    if database_hostname:
        return database_hostname
    else:
        return res[0]

def which_conf_file ():
    res = socket.gethostbyaddr(socket.gethostname())
    # In case we allow local config files per user, try if one exists
    if Cnf.FindB("Config::" + res[0] + "::AllowLocalConfig"):
        homedir = os.getenv("HOME")
        confpath = os.path.join(homedir, "/etc/dak.conf")
        if os.path.exists(confpath):
            apt_pkg.ReadConfigFileISC(Cnf,default_config)

    # We are still in here, so there is no local config file or we do
    # not allow local files. Do the normal stuff.
    if Cnf.get("Config::" + res[0] + "::DakConfig"):
        return Cnf["Config::" + res[0] + "::DakConfig"]
    else:
        return default_config

def which_apt_conf_file ():
    res = socket.gethostbyaddr(socket.gethostname())
    # In case we allow local config files per user, try if one exists
    if Cnf.FindB("Config::" + res[0] + "::AllowLocalConfig"):
        homedir = os.getenv("HOME")
        confpath = os.path.join(homedir, "/etc/dak.conf")
        if os.path.exists(confpath):
            apt_pkg.ReadConfigFileISC(Cnf,default_config)

    if Cnf.get("Config::" + res[0] + "::AptConfig"):
        return Cnf["Config::" + res[0] + "::AptConfig"]
    else:
        return default_apt_config

def which_alias_file():
    hostname = socket.gethostbyaddr(socket.gethostname())[0]
    aliasfn = '/var/lib/misc/'+hostname+'/forward-alias'
    if os.path.exists(aliasfn):
        return aliasfn
    else:
        return None

################################################################################

# Escape characters which have meaning to SQL's regex comparison operator ('~')
# (woefully incomplete)

def regex_safe (s):
    s = s.replace('+', '\\\\+')
    s = s.replace('.', '\\\\.')
    return s

################################################################################

def TemplateSubst(map, filename):
    """ Perform a substition of template """
    templatefile = open_file(filename)
    template = templatefile.read()
    for x in map.keys():
        template = template.replace(x,map[x])
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
    q = apt_pkg.VersionCompare(a_version, b_version)
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
    while os.path.exists(dest) and extra < too_many:
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
    # Process suite
    if Options["Suite"]:
        suite_ids_list = []
        for suite in split_args(Options["Suite"]):
            suite_id = database.get_suite_id(suite)
            if suite_id == -1:
                warn("suite '%s' not recognised." % (suite))
            else:
                suite_ids_list.append(suite_id)
        if suite_ids_list:
            con_suites = "AND su.id IN (%s)" % ", ".join([ str(i) for i in suite_ids_list ])
        else:
            fubar("No valid suite given.")
    else:
        con_suites = ""

    # Process component
    if Options["Component"]:
        component_ids_list = []
        for component in split_args(Options["Component"]):
            component_id = database.get_component_id(component)
            if component_id == -1:
                warn("component '%s' not recognised." % (component))
            else:
                component_ids_list.append(component_id)
        if component_ids_list:
            con_components = "AND c.id IN (%s)" % ", ".join([ str(i) for i in component_ids_list ])
        else:
            fubar("No valid component given.")
    else:
        con_components = ""

    # Process architecture
    con_architectures = ""
    if Options["Architecture"]:
        arch_ids_list = []
        check_source = 0
        for architecture in split_args(Options["Architecture"]):
            if architecture == "source":
                check_source = 1
            else:
                architecture_id = database.get_architecture_id(architecture)
                if architecture_id == -1:
                    warn("architecture '%s' not recognised." % (architecture))
                else:
                    arch_ids_list.append(architecture_id)
        if arch_ids_list:
            con_architectures = "AND a.id IN (%s)" % ", ".join([ str(i) for i in arch_ids_list ])
        else:
            if not check_source:
                fubar("No valid architecture given.")
    else:
        check_source = 1

    return (con_suites, con_architectures, con_components, check_source)

################################################################################

# Inspired(tm) by Bryn Keller's print_exc_plus (See
# http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52215)

def print_exc():
    tb = sys.exc_info()[2]
    while tb.tb_next:
        tb = tb.tb_next
    stack = []
    frame = tb.tb_frame
    while frame:
        stack.append(frame)
        frame = frame.f_back
    stack.reverse()
    traceback.print_exc()
    for frame in stack:
        print "\nFrame %s in %s at line %s" % (frame.f_code.co_name,
                                             frame.f_code.co_filename,
                                             frame.f_lineno)
        for key, value in frame.f_locals.items():
            print "\t%20s = " % key,
            try:
                print value
            except:
                print "<unable to print>"

################################################################################

def try_with_debug(function):
    try:
        function()
    except SystemExit:
        raise
    except:
        print_exc()

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

def Dict(**dict): return dict

########################################

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
        keyring = Cnf.ValueList("Dinstall::GPGKeyring")[0]

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
        keyrings = Cnf.ValueList("Dinstall::GPGKeyring")

    return " ".join(["--keyring %s" % x for x in keyrings])

################################################################################

def check_signature (sig_filename, reject, data_filename="", keyrings=None, autofetch=None):
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

    # Ensure the filename contains no shell meta-characters or other badness
    if not re_taint_free.match(sig_filename):
        reject("!!WARNING!! tainted signature filename: '%s'." % (sig_filename))
        return None

    if data_filename and not re_taint_free.match(data_filename):
        reject("!!WARNING!! tainted data filename: '%s'." % (data_filename))
        return None

    if not keyrings:
        keyrings = Cnf.ValueList("Dinstall::GPGKeyring")

    # Autofetch the signing key if that's enabled
    if autofetch == None:
        autofetch = Cnf.get("Dinstall::KeyAutoFetch")
    if autofetch:
        error_msg = retrieve_key(sig_filename)
        if error_msg:
            reject(error_msg)
            return None

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
        reject("internal error while performing signature check on %s." % (sig_filename))
        reject(internal_error, "")
        reject("Please report the above errors to the Archive maintainers by replying to this mail.", "")
        return None

    bad = ""
    # Now check for obviously bad things in the processed output
    if keywords.has_key("KEYREVOKED"):
        reject("The key used to sign %s has been revoked." % (sig_filename))
        bad = 1
    if keywords.has_key("BADSIG"):
        reject("bad signature on %s." % (sig_filename))
        bad = 1
    if keywords.has_key("ERRSIG") and not keywords.has_key("NO_PUBKEY"):
        reject("failed to check signature on %s." % (sig_filename))
        bad = 1
    if keywords.has_key("NO_PUBKEY"):
        args = keywords["NO_PUBKEY"]
        if len(args) >= 1:
            key = args[0]
        reject("The key (0x%s) used to sign %s wasn't found in the keyring(s)." % (key, sig_filename))
        bad = 1
    if keywords.has_key("BADARMOR"):
        reject("ASCII armour of signature was corrupt in %s." % (sig_filename))
        bad = 1
    if keywords.has_key("NODATA"):
        reject("no signature found in %s." % (sig_filename))
        bad = 1
    if keywords.has_key("EXPKEYSIG"):
        args = keywords["EXPKEYSIG"]
        if len(args) >= 1:
            key = args[0]
        reject("Signature made by expired key 0x%s" % (key))
        bad = 1
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
        reject("The key used to sign %s has expired on %s" % (sig_filename, expiredate))
        bad = 1

    if bad:
        return None

    # Next check gpgv exited with a zero return code
    if exit_status:
        reject("gpgv failed while checking %s." % (sig_filename))
        if status.strip():
            reject(prefix_multi_line_string(status, " [GPG status-fd output:] "), "")
        else:
            reject(prefix_multi_line_string(output, " [GPG output:] "), "")
        return None

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        reject("signature on %s does not appear to be valid [No VALIDSIG]." % (sig_filename))
        bad = 1
    else:
        args = keywords["VALIDSIG"]
        if len(args) < 1:
            reject("internal error while checking signature on %s." % (sig_filename))
            bad = 1
        else:
            fingerprint = args[0]
    if not keywords.has_key("GOODSIG"):
        reject("signature on %s does not appear to be valid [No GOODSIG]." % (sig_filename))
        bad = 1
    if not keywords.has_key("SIG_ID"):
        reject("signature on %s does not appear to be valid [No SIG_ID]." % (sig_filename))
        bad = 1

    # Finally ensure there's not something we don't recognise
    known_keywords = Dict(VALIDSIG="",SIG_ID="",GOODSIG="",BADSIG="",ERRSIG="",
                          SIGEXPIRED="",KEYREVOKED="",NO_PUBKEY="",BADARMOR="",
                          NODATA="",NOTATION_DATA="",NOTATION_NAME="",KEYEXPIRED="")

    for keyword in keywords.keys():
        if not known_keywords.has_key(keyword):
            reject("found unknown status token '%s' from gpgv with args '%r' in %s." % (keyword, keywords[keyword], sig_filename))
            bad = 1

    if bad:
        return None
    else:
        return fingerprint

################################################################################

def gpg_get_key_addresses(fingerprint):
    """retreive email addresses from gpg key uids for a given fingerprint"""
    addresses = key_uid_email_cache.get(fingerprint)
    if addresses != None:
        return addresses
    addresses = set()
    cmd = "gpg --no-default-keyring %s --fingerprint %s" \
                % (gpg_keyring_args(), fingerprint)
    (result, output) = commands.getstatusoutput(cmd)
    if result == 0:
        for l in output.split('\n'):
            m = re_gpg_uid.match(l)
            if m:
                addresses.add(m.group(1))
    key_uid_email_cache[fingerprint] = addresses
    return addresses

################################################################################

# Inspired(tm) by http://www.zopelabs.com/cookbook/1022242603

def wrap(paragraph, max_length, prefix=""):
    line = ""
    s = ""
    have_started = 0
    words = paragraph.split()

    for word in words:
        word_size = len(word)
        if word_size > max_length:
            if have_started:
                s += line + '\n' + prefix
            s += word + '\n' + prefix
        else:
            if have_started:
                new_length = len(line) + word_size + 1
                if new_length > max_length:
                    s += line + '\n' + prefix
                    line = word
                else:
                    line += ' ' + word
            else:
                line = word
        have_started = 1

    if have_started:
        s += line

    return s

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

def temp_filename(directory=None, prefix="dak", suffix=""):
    """
    Return a secure and unique filename by pre-creating it.
    If 'directory' is non-null, it will be the directory the file is pre-created in.
    If 'prefix' is non-null, the filename will be prefixed with it, default is dak.
    If 'suffix' is non-null, the filename will end with it.

    Returns a pair (fd, name).
    """

    return tempfile.mkstemp(suffix, prefix, directory)

################################################################################

def temp_dirname(parent=None, prefix="dak", suffix=""):
    """
    Return a secure and unique directory by pre-creating it.
    If 'parent' is non-null, it will be the directory the directory is pre-created in.
    If 'prefix' is non-null, the filename will be prefixed with it, default is dak.
    If 'suffix' is non-null, the filename will end with it.

    Returns a pathname to the new directory
    """

    return tempfile.mkdtemp(suffix, prefix, parent)

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

def get_changes_files(dir):
    """
    Takes a directory and lists all .changes files in it (as well as chdir'ing
    to the directory; this is due to broken behaviour on the part of p-u/p-a
    when you're not in the right place)

    Returns a list of filenames
    """
    try:
        # Much of the rest of p-u/p-a depends on being in the right place
        os.chdir(dir)
        changes_files = [x for x in os.listdir(dir) if x.endswith('.changes')]
    except OSError, e:
        fubar("Failed to read list from directory %s (%s)" % (dir, e))

    return changes_files

################################################################################

apt_pkg.init()

Cnf = apt_pkg.newConfiguration()
apt_pkg.ReadConfigFileISC(Cnf,default_config)

#if which_conf_file() != default_config:
#    apt_pkg.ReadConfigFileISC(Cnf,which_conf_file())

###############################################################################
