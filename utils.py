# Utility functions
# Copyright (C) 2000, 2001  James Troup <james@nocrew.org>
# $Id: utils.py,v 1.30 2001-07-25 15:51:15 troup Exp $

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

import commands, os, pwd, re, socket, shutil, stat, string, sys, tempfile
import apt_pkg

re_comments = re.compile(r"\#.*")
re_no_epoch = re.compile(r"^\d*\:")
re_no_revision = re.compile(r"\-[^-]*$")
re_arch_from_filename = re.compile(r"/binary-[^/]+/")
re_extract_src_version = re.compile (r"(\S+)\s*\((.*)\)")
re_isadeb = re.compile (r".*\.u?deb$");
re_issource = re.compile (r"(.+)_(.+?)\.(orig\.tar\.gz|diff\.gz|tar\.gz|dsc)");

re_begin_pgp_signature = re.compile("^-----BEGIN PGP SIGNATURE");
re_begin_pgp_signed_msg = re.compile("^-----BEGIN PGP SIGNED MESSAGE");
re_single_line_field = re.compile(r"^(\S*)\s*:\s*(.*)");
re_multi_line_description = re.compile(r"^ \.$");
re_multi_line_field = re.compile(r"^\s(.*)");

re_parse_maintainer = re.compile(r"^\s*(\S.*\S)\s*\<([^\> \t]+)\>");

changes_parse_error_exc = "Can't parse line in .changes file";
invalid_dsc_format_exc = "Invalid .dsc file";
nk_format_exc = "Unknown Format: in .changes file";
no_files_exc = "No Files: field in .dsc file.";
cant_open_exc = "Can't read file.";
unknown_hostname_exc = "Unknown hostname";
cant_overwrite_exc = "Permission denied; can't overwrite existent file."
file_exists_exc = "Destination file exists";
send_mail_invalid_args_exc = "Both arguments are non-null.";
sendmail_failed_exc = "Sendmail invocation failed";
tried_too_hard_exc = "Tried too hard to find a free filename.";

# Valid components; used by extract_component_from_section() because
# it doesn't know about Conf from it's caller.  FIXME

valid_components = {
    "main": "",
    "contrib": "",
    "non-free": ""
    };

######################################################################################

def open_file(filename, mode='r'):
    try:
	f = open(filename, mode);
    except IOError:
        raise cant_open_exc, filename
    return f

######################################################################################

# From reportbug
def our_raw_input():
    sys.stdout.flush()
    try:
        ret = raw_input()
        return ret
    except EOFError:
        sys.stderr.write('\nUser interrupt (^D).\n')
        raise SystemExit

######################################################################################

def str_isnum (s):
    for c in s:
        if c not in string.digits:
            return 0;
    return 1;

######################################################################################

# Prefix and components hardcoded into this like a good'un; need to unhardcod at some
# stage. [FIXME]

def extract_component_from_section(section):
    component = "";
    
    if string.find(section, '/') != -1: 
        component = string.split(section, '/')[0];
    if string.lower(component) == "non-us" and string.count(section, '/') > 0:
        s = string.split(section, '/')[1];
        if valid_components.has_key(s): # Avoid e.g. non-US/libs
            component = string.split(section, '/')[0]+ '/' + string.split(section, '/')[1];

    if string.lower(section) == "non-us":
        component = "non-US/main";

    # non-US prefix is case insensitive
    if string.lower(component)[:6] == "non-us":
        component = "non-US"+component[6:];

    # Expand default component
    if component == "":
        if valid_components.has_key(section):
            component = section;
        else:
            component = "main";
    elif component == "non-US":
        component = "non-US/main";

    return (section, component);

######################################################################################

# dsc_whitespace_rules turns on strict format checking to avoid
# allowing in source packages which are unextracable by the
# inappropriately fragile dpkg-source.
#
# The rules are:
#
#
# o The PGP header consists of "-----BEGIN PGP SIGNED MESSAGE-----"
#   followed by any PGP header data and must end with a blank line.
#
# o The data section must end with a blank line and must be followed by
#   "-----BEGIN PGP SIGNATURE-----".

def parse_changes(filename, dsc_whitespace_rules):
    changes_in = open_file(filename,'r');
    error = "";
    changes = {};
    lines = changes_in.readlines();

    if lines == []:
	raise changes_parse_error_exc, "[Empty changes file]";

    # Reindex by line number so we can easily verify the format of
    # .dsc files...
    index = 0;
    indexed_lines = {};
    for line in lines:
        index = index + 1;
        indexed_lines[index] = line[:-1];

    inside_signature = 0;

    indices = indexed_lines.keys()
    index = 0;
    while index < max(indices):
        index = index + 1;
        line = indexed_lines[index];
        if line == "":
            if dsc_whitespace_rules:
                index = index + 1;
                if index > max(indices):
                    raise invalid_dsc_format_exc, index;
                line = indexed_lines[index];
                if not re_begin_pgp_signature.match(line):
                    raise invalid_dsc_format_exc, index;
                inside_signature = 0;
                break;
        if re_begin_pgp_signature.match(line):
            break;
        if re_begin_pgp_signed_msg.match(line):
            if dsc_whitespace_rules:
                inside_signature = 1;
                while index < max(indices) and line != "":
                    index = index + 1;
                    line = indexed_lines[index];
            continue;
        slf = re_single_line_field.match(line);
        if slf:
            field = string.lower(slf.groups()[0]);
            changes[field] = slf.groups()[1];
	    first = 1;
            continue;
        mld = re_multi_line_description.match(line);
        if mld:
            changes[field] = changes[field] + '\n';
            continue;
        mlf = re_multi_line_field.match(line);
        if mlf:
            if first == 1 and changes[field] != "":
                changes[field] = changes[field] + '\n';
            first = 0;
	    changes[field] = changes[field] + mlf.groups()[0] + '\n';
            continue;
	error = error + line;

    if dsc_whitespace_rules and inside_signature:
        raise invalid_dsc_format_exc, index;
        
    changes_in.close();
    changes["filecontents"] = string.join (lines, "");

    if error != "":
	raise changes_parse_error_exc, error;

    return changes;

######################################################################################

# Dropped support for 1.4 and ``buggy dchanges 3.4'' (?!) compared to di.pl

def build_file_list(changes, dsc):
    files = {}
    format = changes.get("format", "")
    if format != "":
	format = float(format)
    if dsc == "" and (format < 1.5 or format > 2.0):
	raise nk_format_exc, format;

    # No really, this has happened.  Think 0 length .dsc file.
    if not changes.has_key("files"):
	raise no_files_exc
    
    for i in string.split(changes["files"], "\n"):
        if i == "":
            break
        s = string.split(i)
        section = priority = "";
        try:
            if dsc != "":
                (md5, size, name) = s
            else:
                (md5, size, section, priority, name) = s
        except ValueError:
            raise changes_parse_error_exc, i

        if section == "": section = "-"
        if priority == "": priority = "-"

        (section, component) = extract_component_from_section(section);
        
        files[name] = { "md5sum" : md5,
                        "size" : size,
                        "section": section,
                        "priority": priority,
                        "component": component }

    return files

######################################################################################

# Fix the `Maintainer:' field to be an RFC822 compatible address.
# cf. Packaging Manual (4.2.4)
#
# 06:28|<Culus> 'The standard sucks, but my tool is supposed to
#                interoperate with it. I know - I'll fix the suckage
#                and make things incompatible!'
        
def fix_maintainer (maintainer):
    m = re_parse_maintainer.match(maintainer);
    rfc822 = maintainer
    name = ""
    email = ""
    if m != None and len(m.groups()) == 2:
        name = m.group(1)
        email = m.group(2)
        if string.find(name, ',') != -1 or string.find(name, '.') != -1:
            rfc822 = re_parse_maintainer.sub(r"\2 (\1)", maintainer)
    return (rfc822, name, email)

######################################################################################

# sendmail wrapper, takes _either_ a message string or a file as arguments
def send_mail (message, filename):
	#### FIXME, how do I get this out of Cnf in katie?
	sendmail_command = "/usr/sbin/sendmail -odq -oi -t";

	# Sanity check arguments
	if message != "" and filename != "":
            raise send_mail_invalid_args_exc;

	# If we've been passed a string dump it into a temporary file
	if message != "":
            filename = tempfile.mktemp();
            fd = os.open(filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0700);
            os.write (fd, message);
            os.close (fd);

	# Invoke sendmail
	(result, output) = commands.getstatusoutput("%s < %s" % (sendmail_command, filename));
	if (result != 0):
            raise sendmail_failed_exc, output;

	# Clean up any temporary files
	if message !="":
            os.unlink (filename);

######################################################################################

def poolify (source, component):
    if component != "":
	component = component + '/';
    # FIXME: this is nasty
    component = string.lower(component);
    component = string.replace(component, 'non-us/', 'non-US/');
    if source[:3] == "lib":
	return component + source[:4] + '/' + source + '/'
    else:
	return component + source[:1] + '/' + source + '/'

######################################################################################

def move (src, dest, overwrite = 0):
    if os.path.exists(dest) and os.path.isdir(dest):
	dest_dir = dest;
    else:
	dest_dir = os.path.dirname(dest);
    if not os.path.exists(dest_dir):
	umask = os.umask(00000);
	os.makedirs(dest_dir, 02775);
	os.umask(umask);
    #print "Moving %s to %s..." % (src, dest);
    if os.path.exists(dest) and os.path.isdir(dest):
	dest = dest + '/' + os.path.basename(src);
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            raise file_exists_exc;
        else:
            if not os.access(dest, os.W_OK):
                raise cant_overwrite_exc
    shutil.copy2(src, dest);
    os.chmod(dest, 0664);
    os.unlink(src);

def copy (src, dest, overwrite = 0):
    if os.path.exists(dest) and os.path.isdir(dest):
	dest_dir = dest;
    else:
	dest_dir = os.path.dirname(dest);
    if not os.path.exists(dest_dir):
	umask = os.umask(00000);
	os.makedirs(dest_dir, 02775);
	os.umask(umask);
    #print "Copying %s to %s..." % (src, dest);
    if os.path.exists(dest) and os.path.isdir(dest):
	dest = dest + '/' + os.path.basename(src);
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            raise file_exists_exc
        else:
            if not os.access(dest, os.W_OK):
                raise cant_overwrite_exc
    shutil.copy2(src, dest);
    os.chmod(dest, 0664);

######################################################################################

# FIXME: this is inherently nasty.  Can't put this mapping in a conf
# file because the conf file depends on the archive.. doh.  Maybe an
# archive independent conf file is needed.

def where_am_i ():
    res = socket.gethostbyaddr(socket.gethostname());
    if res[0] == 'pandora.debian.org':
        return 'non-US';
    elif res[0] == 'auric.debian.org':
        return 'ftp-master';
    else:
        raise unknown_hostname_exc, res;

######################################################################################

# FIXME: this isn't great either.

def which_conf_file ():
    archive = where_am_i ();
    if archive == 'non-US':
        return '/org/non-us.debian.org/katie/katie.conf-non-US';
    elif archive == 'ftp-master':
        return '/org/ftp.debian.org/katie/katie.conf';
    else:
        raise unknown_hostname_exc, archive

# FIXME: if the above isn't great, this can't be either :)

def which_apt_conf_file ():
    archive = where_am_i ();
    if archive == 'non-US':
        return '/org/non-us.debian.org/katie/apt.conf-non-US';
    elif archive == 'ftp-master':
        return '/org/ftp.debian.org/katie/apt.conf';
    else:
        raise unknown_hostname_exc, archive

######################################################################################

# Escape characters which have meaning to SQL's regex comparison operator ('~')
# (woefully incomplete)

def regex_safe (s):
    s = string.replace(s, '+', '\\\\+');
    s = string.replace(s, '.', '\\\\.');
    return s

######################################################################################

# Perform a substition of template 
def TemplateSubst(Map,Template):
    for x in Map.keys():
        Template = string.replace(Template,x,Map[x]);
    return Template;

######################################################################################

def fubar(msg, exit_code=1):
    sys.stderr.write("E: %s\n" % (msg));
    sys.exit(exit_code);

def warn(msg):
    sys.stderr.write("W: %s\n" % (msg));

######################################################################################

# Returns the user name with a laughable attempt at rfc822 conformancy
# (read: removing stray periods).
def whoami ():
    return string.replace(string.split(pwd.getpwuid(os.getuid())[4],',')[0], '.', '');

######################################################################################

def size_type (c):
    t  = " b";
    if c > 10000:
        c = c / 1000;
        t = " Kb";
    if c > 10000:
        c = c / 1000;
        t = " Mb";
    return ("%d%s" % (c, t))

################################################################################

def cc_fix_changes (changes):
    o = changes.get("architecture", "")
    if o != "":
        del changes["architecture"]
    changes["architecture"] = {}
    for j in string.split(o):
        changes["architecture"][j] = 1

# Sort by 'have source', by source name, by source version number, by filename

def changes_compare (a, b):
    try:
        a_changes = parse_changes(a, 0)
    except:
        return -1;

    try:
        b_changes = parse_changes(b, 0)
    except:
        return 1;
    
    cc_fix_changes (a_changes);
    cc_fix_changes (b_changes);

    # Sort by 'have source'

    a_has_source = a_changes["architecture"].get("source")
    b_has_source = b_changes["architecture"].get("source")
    if a_has_source and not b_has_source:
        return -1;
    elif b_has_source and not a_has_source:
        return 1;

    # Sort by source name
    
    a_source = a_changes.get("source");
    b_source = b_changes.get("source");
    q = cmp (a_source, b_source);
    if q:
        return q;

    # Sort by source version

    a_version = a_changes.get("version");
    b_version = b_changes.get("version");
    q = apt_pkg.VersionCompare(a_version, b_version);
    if q:
        return q

    # Fall back to sort by filename

    return cmp(a, b);

################################################################################

def find_next_free (dest, too_many=100):
    extra = 0;
    orig_dest = dest;
    while os.path.exists(dest) and extra < too_many:
        dest = orig_dest + '.' + repr(extra);
        extra = extra + 1;
    if extra >= too_many:
        raise tried_too_hard_exc;
    return dest;
    
################################################################################
