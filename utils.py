#!/usr/bin/env python

# Utility functions
# Copyright (C) 2000, 2001, 2002, 2003, 2004  James Troup <james@nocrew.org>
# $Id: utils.py,v 1.61 2004-01-21 03:20:52 troup Exp $

################################################################################

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

import commands, os, pwd, re, select, socket, shutil, string, sys, tempfile, traceback;
import apt_pkg;
import db_access;

################################################################################

re_comments = re.compile(r"\#.*")
re_no_epoch = re.compile(r"^\d*\:")
re_no_revision = re.compile(r"\-[^-]*$")
re_arch_from_filename = re.compile(r"/binary-[^/]+/")
re_extract_src_version = re.compile (r"(\S+)\s*\((.*)\)")
re_isadeb = re.compile (r"(.+?)_(.+?)_(.+)\.u?deb$");
re_issource = re.compile (r"(.+)_(.+?)\.(orig\.tar\.gz|diff\.gz|tar\.gz|dsc)$");

re_single_line_field = re.compile(r"^(\S*)\s*:\s*(.*)");
re_multi_line_field = re.compile(r"^\s(.*)");
re_taint_free = re.compile(r"^[-+~\.\w]+$");

re_parse_maintainer = re.compile(r"^\s*(\S.*\S)\s*\<([^\> \t]+)\>");

changes_parse_error_exc = "Can't parse line in .changes file";
invalid_dsc_format_exc = "Invalid .dsc file";
nk_format_exc = "Unknown Format: in .changes file";
no_files_exc = "No Files: field in .dsc file.";
cant_open_exc = "Can't read file.";
unknown_hostname_exc = "Unknown hostname";
cant_overwrite_exc = "Permission denied; can't overwrite existent file."
file_exists_exc = "Destination file exists";
sendmail_failed_exc = "Sendmail invocation failed";
tried_too_hard_exc = "Tried too hard to find a free filename.";

default_config = "/etc/katie/katie.conf";
default_apt_config = "/etc/katie/apt.conf";

################################################################################

def open_file(filename, mode='r'):
    try:
	f = open(filename, mode);
    except IOError:
        raise cant_open_exc, filename;
    return f

################################################################################

def our_raw_input(prompt=""):
    if prompt:
        sys.stdout.write(prompt);
    sys.stdout.flush();
    try:
        ret = raw_input();
        return ret;
    except EOFError:
        sys.stderr.write("\nUser interrupt (^D).\n");
        raise SystemExit;

################################################################################

def str_isnum (s):
    for c in s:
        if c not in string.digits:
            return 0;
    return 1;

################################################################################

def extract_component_from_section(section):
    component = "";

    if section.find('/') != -1:
        component = section.split('/')[0];
    if component.lower() == "non-us" and section.count('/') > 0:
        s = component + '/' + section.split('/')[1];
        if Cnf.has_key("Component::%s" % s): # Avoid e.g. non-US/libs
            component = s;

    if section.lower() == "non-us":
        component = "non-US/main";

    # non-US prefix is case insensitive
    if component.lower()[:6] == "non-us":
        component = "non-US"+component[6:];

    # Expand default component
    if component == "":
        if Cnf.has_key("Component::%s" % section):
            component = section;
        else:
            component = "main";
    elif component == "non-US":
        component = "non-US/main";

    return (section, component);

################################################################################

# Parses a changes file and returns a dictionary where each field is a
# key.  The mandatory first argument is the filename of the .changes
# file.

# dsc_whitespace_rules is an optional boolean argument which defaults
# to off.  If true, it turns on strict format checking to avoid
# allowing in source packages which are unextracable by the
# inappropriately fragile dpkg-source.
#
# The rules are:
#
#   o The PGP header consists of "-----BEGIN PGP SIGNED MESSAGE-----"
#     followed by any PGP header data and must end with a blank line.
#
#   o The data section must end with a blank line and must be followed by
#     "-----BEGIN PGP SIGNATURE-----".

def parse_changes(filename, dsc_whitespace_rules=0):
    error = "";
    changes = {};

    changes_in = open_file(filename);
    lines = changes_in.readlines();

    if not lines:
	raise changes_parse_error_exc, "[Empty changes file]";

    # Reindex by line number so we can easily verify the format of
    # .dsc files...
    index = 0;
    indexed_lines = {};
    for line in lines:
        index += 1;
        indexed_lines[index] = line[:-1];

    inside_signature = 0;

    num_of_lines = len(indexed_lines.keys());
    index = 0;
    first = -1;
    while index < num_of_lines:
        index += 1;
        line = indexed_lines[index];
        if line == "":
            if dsc_whitespace_rules:
                index += 1;
                if index > num_of_lines:
                    raise invalid_dsc_format_exc, index;
                line = indexed_lines[index];
                if not line.startswith("-----BEGIN PGP SIGNATURE"):
                    raise invalid_dsc_format_exc, index;
                inside_signature = 0;
                break;
            else:
                continue;
        if line.startswith("-----BEGIN PGP SIGNATURE"):
            break;
        if line.startswith("-----BEGIN PGP SIGNED MESSAGE"):
            if dsc_whitespace_rules:
                inside_signature = 1;
                while index < num_of_lines and line != "":
                    index += 1;
                    line = indexed_lines[index];
            continue;
        # If we're not inside the signed data, don't process anything
        if not inside_signature:
            continue;
        slf = re_single_line_field.match(line);
        if slf:
            field = slf.groups()[0].lower();
            changes[field] = slf.groups()[1];
	    first = 1;
            continue;
        if line == " .":
            changes[field] += '\n';
            continue;
        mlf = re_multi_line_field.match(line);
        if mlf:
            if first == -1:
                raise changes_parse_error_exc, "'%s'\n [Multi-line field continuing on from nothing?]" % (line);
            if first == 1 and changes[field] != "":
                changes[field] += '\n';
            first = 0;
	    changes[field] += mlf.groups()[0] + '\n';
            continue;
	error += line;

    if dsc_whitespace_rules and inside_signature:
        raise invalid_dsc_format_exc, index;

    changes_in.close();
    changes["filecontents"] = "".join(lines);

    if error:
	raise changes_parse_error_exc, error;

    return changes;

################################################################################

# Dropped support for 1.4 and ``buggy dchanges 3.4'' (?!) compared to di.pl

def build_file_list(changes, is_a_dsc=0):
    files = {};

    # Make sure we have a Files: field to parse...
    if not changes.has_key("files"):
	raise no_files_exc;

    # Make sure we recognise the format of the Files: field
    format = changes.get("format", "");
    if format != "":
	format = float(format);
    if not is_a_dsc and (format < 1.5 or format > 2.0):
	raise nk_format_exc, format;

    # Parse each entry/line:
    for i in changes["files"].split('\n'):
        if not i:
            break;
        s = i.split();
        section = priority = "";
        try:
            if is_a_dsc:
                (md5, size, name) = s;
            else:
                (md5, size, section, priority, name) = s;
        except ValueError:
            raise changes_parse_error_exc, i;

        if section == "":
            section = "-";
        if priority == "":
            priority = "-";

        (section, component) = extract_component_from_section(section);

        files[name] = Dict(md5sum=md5, size=size, section=section,
                           priority=priority, component=component);

    return files

################################################################################

# Fix the `Maintainer:' field to be an RFC822 compatible address.
# cf. Debian Policy Manual (D.2.4)
#
# 06:28|<Culus> 'The standard sucks, but my tool is supposed to
#                interoperate with it. I know - I'll fix the suckage
#                and make things incompatible!'

def fix_maintainer (maintainer):
    m = re_parse_maintainer.match(maintainer);
    rfc822 = maintainer;
    name = "";
    email = "";
    if m != None and len(m.groups()) == 2:
        name = m.group(1);
        email = m.group(2);
        if name.find(',') != -1 or name.find('.') != -1:
            rfc822 = "%s (%s)" % (email, name);
    return (rfc822, name, email)

################################################################################

# sendmail wrapper, takes _either_ a message string or a file as arguments
def send_mail (message, filename=""):
	# If we've been passed a string dump it into a temporary file
	if message:
            filename = tempfile.mktemp();
            fd = os.open(filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0700);
            os.write (fd, message);
            os.close (fd);

	# Invoke sendmail
	(result, output) = commands.getstatusoutput("%s < %s" % (Cnf["Dinstall::SendmailCommand"], filename));
	if (result != 0):
            raise sendmail_failed_exc, output;

	# Clean up any temporary files
	if message:
            os.unlink (filename);

################################################################################

def poolify (source, component):
    if component:
	component += '/';
    # FIXME: this is nasty
    component = component.lower().replace("non-us/", "non-US/");
    if source[:3] == "lib":
	return component + source[:4] + '/' + source + '/'
    else:
	return component + source[:1] + '/' + source + '/'

################################################################################

def move (src, dest, overwrite = 0, perms = 0664):
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
	dest += '/' + os.path.basename(src);
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            fubar("Can't move %s to %s - file already exists." % (src, dest));
        else:
            if not os.access(dest, os.W_OK):
                fubar("Can't move %s to %s - can't write to existing file." % (src, dest));
    shutil.copy2(src, dest);
    os.chmod(dest, perms);
    os.unlink(src);

def copy (src, dest, overwrite = 0, perms = 0664):
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
	dest += '/' + os.path.basename(src);
    # Don't overwrite unless forced to
    if os.path.exists(dest):
        if not overwrite:
            raise file_exists_exc
        else:
            if not os.access(dest, os.W_OK):
                raise cant_overwrite_exc
    shutil.copy2(src, dest);
    os.chmod(dest, perms);

################################################################################

def where_am_i ():
    res = socket.gethostbyaddr(socket.gethostname());
    database_hostname = Cnf.get("Config::" + res[0] + "::DatabaseHostname");
    if database_hostname:
	return database_hostname;
    else:
        return res[0];

def which_conf_file ():
    res = socket.gethostbyaddr(socket.gethostname());
    if Cnf.get("Config::" + res[0] + "::KatieConfig"):
	return Cnf["Config::" + res[0] + "::KatieConfig"]
    else:
	return default_config;

def which_apt_conf_file ():
    res = socket.gethostbyaddr(socket.gethostname());
    if Cnf.get("Config::" + res[0] + "::AptConfig"):
	return Cnf["Config::" + res[0] + "::AptConfig"]
    else:
	return default_apt_config;

################################################################################

# Escape characters which have meaning to SQL's regex comparison operator ('~')
# (woefully incomplete)

def regex_safe (s):
    s = s.replace('+', '\\\\+');
    s = s.replace('.', '\\\\.');
    return s

################################################################################

# Perform a substition of template
def TemplateSubst(map, filename):
    file = open_file(filename);
    template = file.read();
    for x in map.keys():
        template = template.replace(x,map[x]);
    file.close();
    return template;

################################################################################

def fubar(msg, exit_code=1):
    sys.stderr.write("E: %s\n" % (msg));
    sys.exit(exit_code);

def warn(msg):
    sys.stderr.write("W: %s\n" % (msg));

################################################################################

# Returns the user name with a laughable attempt at rfc822 conformancy
# (read: removing stray periods).
def whoami ():
    return pwd.getpwuid(os.getuid())[4].split(',')[0].replace('.', '');

################################################################################

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
    o = changes.get("architecture", "");
    if o:
        del changes["architecture"];
    changes["architecture"] = {};
    for j in o.split():
        changes["architecture"][j] = 1;

# Sort by source name, source version, 'have source', and then by filename
def changes_compare (a, b):
    try:
        a_changes = parse_changes(a);
    except:
        return -1;

    try:
        b_changes = parse_changes(b);
    except:
        return 1;

    cc_fix_changes (a_changes);
    cc_fix_changes (b_changes);

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
        return q;

    # Sort by 'have source'
    a_has_source = a_changes["architecture"].get("source");
    b_has_source = b_changes["architecture"].get("source");
    if a_has_source and not b_has_source:
        return -1;
    elif b_has_source and not a_has_source:
        return 1;

    # Fall back to sort by filename
    return cmp(a, b);

################################################################################

def find_next_free (dest, too_many=100):
    extra = 0;
    orig_dest = dest;
    while os.path.exists(dest) and extra < too_many:
        dest = orig_dest + '.' + repr(extra);
        extra += 1;
    if extra >= too_many:
        raise tried_too_hard_exc;
    return dest;

################################################################################

def result_join (original, sep = '\t'):
    list = [];
    for i in xrange(len(original)):
        if original[i] == None:
            list.append("");
        else:
            list.append(original[i]);
    return sep.join(list);

################################################################################

def prefix_multi_line_string(str, prefix, include_blank_lines=0):
    out = "";
    for line in str.split('\n'):
        line = line.strip();
        if line or include_blank_lines:
            out += "%s%s\n" % (prefix, line);
    # Strip trailing new line
    if out:
        out = out[:-1];
    return out;

################################################################################

def validate_changes_file_arg(file, fatal=1):
    error = None;

    orig_filename = file
    if file.endswith(".katie"):
        file = file[:-6]+".changes";

    if not file.endswith(".changes"):
        error = "invalid file type; not a changes file";
    else:
        if not os.access(file,os.R_OK):
            if os.path.exists(file):
                error = "permission denied";
            else:
                error = "file not found";

    if error:
        if fatal:
            fubar("%s: %s." % (orig_filename, error));
        else:
            warn("Skipping %s - %s" % (orig_filename, error));
            return None;
    else:
        return file;

################################################################################

def real_arch(arch):
    return (arch != "source" and arch != "all");

################################################################################

def join_with_commas_and(list):
	if len(list) == 0: return "nothing";
	if len(list) == 1: return list[0];
	return ", ".join(list[:-1]) + " and " + list[-1];

################################################################################

def get_conf():
	return Cnf;

################################################################################

# Handle -a, -c and -s arguments; returns them as SQL constraints
def parse_args(Options):
    # Process suite
    if Options["Suite"]:
        suite_ids_list = [];
        for suite in split_args(Options["Suite"]):
            suite_id = db_access.get_suite_id(suite);
            if suite_id == -1:
                warn("suite '%s' not recognised." % (suite));
            else:
                suite_ids_list.append(suite_id);
        if suite_ids_list:
            con_suites = "AND su.id IN (%s)" % ", ".join(map(str, suite_ids_list));
        else:
            fubar("No valid suite given.");
    else:
        con_suites = "";

    # Process component
    if Options["Component"]:
        component_ids_list = [];
        for component in split_args(Options["Component"]):
            component_id = db_access.get_component_id(component);
            if component_id == -1:
                warn("component '%s' not recognised." % (component));
            else:
                component_ids_list.append(component_id);
        if component_ids_list:
            con_components = "AND c.id IN (%s)" % ", ".join(map(str, component_ids_list));
        else:
            fubar("No valid component given.");
    else:
        con_components = "";

    # Process architecture
    con_architectures = "";
    if Options["Architecture"]:
        arch_ids_list = [];
        check_source = 0;
        for architecture in split_args(Options["Architecture"]):
            if architecture == "source":
                check_source = 1;
            else:
                architecture_id = db_access.get_architecture_id(architecture);
                if architecture_id == -1:
                    warn("architecture '%s' not recognised." % (architecture));
                else:
                    arch_ids_list.append(architecture_id);
        if arch_ids_list:
            con_architectures = "AND a.id IN (%s)" % ", ".join(map(str, arch_ids_list));
        else:
            if not check_source:
                fubar("No valid architecture given.");
    else:
        check_source = 1;

    return (con_suites, con_architectures, con_components, check_source);

################################################################################

# Inspired(tm) by Bryn Keller's print_exc_plus (See
# http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52215)

def print_exc():
    tb = sys.exc_info()[2];
    while tb.tb_next:
        tb = tb.tb_next;
    stack = [];
    frame = tb.tb_frame;
    while frame:
        stack.append(frame);
        frame = frame.f_back;
    stack.reverse();
    traceback.print_exc();
    for frame in stack:
        print "\nFrame %s in %s at line %s" % (frame.f_code.co_name,
                                             frame.f_code.co_filename,
                                             frame.f_lineno);
        for key, value in frame.f_locals.items():
            print "\t%20s = " % key,;
            try:
                print value;
            except:
                print "<unable to print>";

################################################################################

def try_with_debug(function):
    try:
        function();
    except SystemExit:
        raise;
    except:
        print_exc();

################################################################################

# Function for use in sorting lists of architectures.
# Sorts normally except that 'source' dominates all others.

def arch_compare_sw (a, b):
    if a == "source" and b == "source":
        return 0;
    elif a == "source":
        return -1;
    elif b == "source":
        return 1;

    return cmp (a, b);

################################################################################

# Split command line arguments which can be separated by either commas
# or whitespace.  If dwim is set, it will complain about string ending
# in comma since this usually means someone did 'madison -a i386, m68k
# foo' or something and the inevitable confusion resulting from 'm68k'
# being treated as an argument is undesirable.

def split_args (s, dwim=1):
    if s.find(",") == -1:
        return s.split();
    else:
        if s[-1:] == "," and dwim:
            fubar("split_args: found trailing comma, spurious space maybe?");
        return s.split(",");

################################################################################

def Dict(**dict): return dict

########################################

# Our very own version of commands.getouputstatus(), hacked to support
# gpgv's status fd.
def gpgv_get_status_output(cmd, status_read, status_write):
    cmd = ['/bin/sh', '-c', cmd];
    p2cread, p2cwrite = os.pipe();
    c2pread, c2pwrite = os.pipe();
    errout, errin = os.pipe();
    pid = os.fork();
    if pid == 0:
        # Child
        os.close(0);
        os.close(1);
        os.dup(p2cread);
        os.dup(c2pwrite);
        os.close(2);
        os.dup(errin);
        for i in range(3, 256):
            if i != status_write:
                try:
                    os.close(i);
                except:
                    pass;
        try:
            os.execvp(cmd[0], cmd);
        finally:
            os._exit(1);

    # Parent
    os.close(p2cread)
    os.dup2(c2pread, c2pwrite);
    os.dup2(errout, errin);

    output = status = "";
    while 1:
        i, o, e = select.select([c2pwrite, errin, status_read], [], []);
        more_data = [];
        for fd in i:
            r = os.read(fd, 8196);
            if len(r) > 0:
                more_data.append(fd);
                if fd == c2pwrite or fd == errin:
                    output += r;
                elif fd == status_read:
                    status += r;
                else:
                    fubar("Unexpected file descriptor [%s] returned from select\n" % (fd));
        if not more_data:
            pid, exit_status = os.waitpid(pid, 0)
            try:
                os.close(status_write);
                os.close(status_read);
                os.close(c2pread);
                os.close(c2pwrite);
                os.close(p2cwrite);
                os.close(errin);
                os.close(errout);
            except:
                pass;
            break;

    return output, status, exit_status;

############################################################


def check_signature (filename, reject):
    """Check the signature of a file and return the fingerprint if the
signature is valid or 'None' if it's not.  The first argument is the
filename whose signature should be checked.  The second argument is a
reject function and is called when an error is found.  The reject()
function must allow for two arguments: the first is the error message,
the second is an optional prefix string.  It's possible for reject()
to be called more than once during an invocation of check_signature()."""

    # Ensure the filename contains no shell meta-characters or other badness
    if not re_taint_free.match(os.path.basename(filename)):
        reject("!!WARNING!! tainted filename: '%s'." % (filename));
        return 0;

    # Invoke gpgv on the file
    status_read, status_write = os.pipe();
    cmd = "gpgv --status-fd %s --keyring %s --keyring %s %s" \
          % (status_write, Cnf["Dinstall::PGPKeyring"], Cnf["Dinstall::GPGKeyring"], filename);
    (output, status, exit_status) = gpgv_get_status_output(cmd, status_read, status_write);

    # Process the status-fd output
    keywords = {};
    bad = internal_error = "";
    for line in status.split('\n'):
        line = line.strip();
        if line == "":
            continue;
        split = line.split();
        if len(split) < 2:
            internal_error += "gpgv status line is malformed (< 2 atoms) ['%s'].\n" % (line);
            continue;
        (gnupg, keyword) = split[:2];
        if gnupg != "[GNUPG:]":
            internal_error += "gpgv status line is malformed (incorrect prefix '%s').\n" % (gnupg);
            continue;
        args = split[2:];
        if keywords.has_key(keyword) and (keyword != "NODATA" and keyword != "SIGEXPIRED"):
            internal_error += "found duplicate status token ('%s').\n" % (keyword);
            continue;
        else:
            keywords[keyword] = args;

    # If we failed to parse the status-fd output, let's just whine and bail now
    if internal_error:
        reject("internal error while performing signature check on %s." % (filename));
        reject(internal_error, "");
        reject("Please report the above errors to the Archive maintainers by replying to this mail.", "");
        return None;

    # Now check for obviously bad things in the processed output
    if keywords.has_key("SIGEXPIRED"):
        reject("The key used to sign %s has expired." % (filename));
        bad = 1;
    if keywords.has_key("KEYREVOKED"):
        reject("The key used to sign %s has been revoked." % (filename));
        bad = 1;
    if keywords.has_key("BADSIG"):
        reject("bad signature on %s." % (filename));
        bad = 1;
    if keywords.has_key("ERRSIG") and not keywords.has_key("NO_PUBKEY"):
        reject("failed to check signature on %s." % (filename));
        bad = 1;
    if keywords.has_key("NO_PUBKEY"):
        args = keywords["NO_PUBKEY"];
        if len(args) >= 1:
            key = args[0];
        reject("The key (0x%s) used to sign %s wasn't found in the keyring(s)." % (key, filename));
        bad = 1;
    if keywords.has_key("BADARMOR"):
        reject("ASCII armour of signature was corrupt in %s." % (filename));
        bad = 1;
    if keywords.has_key("NODATA"):
        reject("no signature found in %s." % (filename));
        bad = 1;

    if bad:
        return None;

    # Next check gpgv exited with a zero return code
    if exit_status:
        reject("gpgv failed while checking %s." % (filename));
        if status.strip():
            reject(prefix_multi_line_string(status, " [GPG status-fd output:] "), "");
        else:
            reject(prefix_multi_line_string(output, " [GPG output:] "), "");
        return None;

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        reject("signature on %s does not appear to be valid [No VALIDSIG]." % (filename));
        bad = 1;
    else:
        args = keywords["VALIDSIG"];
        if len(args) < 1:
            reject("internal error while checking signature on %s." % (filename));
            bad = 1;
        else:
            fingerprint = args[0];
    if not keywords.has_key("GOODSIG"):
        reject("signature on %s does not appear to be valid [No GOODSIG]." % (filename));
        bad = 1;
    if not keywords.has_key("SIG_ID"):
        reject("signature on %s does not appear to be valid [No SIG_ID]." % (filename));
        bad = 1;

    # Finally ensure there's not something we don't recognise
    known_keywords = Dict(VALIDSIG="",SIG_ID="",GOODSIG="",BADSIG="",ERRSIG="",
                          SIGEXPIRED="",KEYREVOKED="",NO_PUBKEY="",BADARMOR="",
                          NODATA="");

    for keyword in keywords.keys():
        if not known_keywords.has_key(keyword):
            reject("found unknown status token '%s' from gpgv with args '%r' in %s." % (keyword, keywords[keyword], filename));
            bad = 1;

    if bad:
        return None;
    else:
        return fingerprint;

################################################################################

# Inspired(tm) by http://www.zopelabs.com/cookbook/1022242603

def wrap(paragraph, max_length, prefix=""):
    line = "";
    s = "";
    have_started = 0;
    words = paragraph.split();

    for word in words:
        word_size = len(word);
        if word_size > max_length:
            if have_started:
                s += line + '\n' + prefix;
            s += word + '\n' + prefix;
        else:
            if have_started:
                new_length = len(line) + word_size + 1;
                if new_length > max_length:
                    s += line + '\n' + prefix;
                    line = word;
                else:
                    line += ' ' + word;
            else:
                line = word;
        have_started = 1;

    if have_started:
        s += line;

    return s;

################################################################################

# Relativize an absolute symlink from 'src' -> 'dest' relative to 'root'.
# Returns fixed 'src'
def clean_symlink (src, dest, root):
    src = src.replace(root, '', 1);
    dest = dest.replace(root, '', 1);
    dest = os.path.dirname(dest);
    new_src = '../' * len(dest.split('/'));
    return new_src + src;

################################################################################

apt_pkg.init();

Cnf = apt_pkg.newConfiguration();
apt_pkg.ReadConfigFileISC(Cnf,default_config);

if which_conf_file() != default_config:
	apt_pkg.ReadConfigFileISC(Cnf,which_conf_file());

################################################################################
