# Utility functions
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: utils.py,v 1.1.1.1 2000-11-24 00:20:09 troup Exp $

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

import commands, os, re, socket, shutil, stat, string, sys, tempfile

re_comments = re.compile(r"\#.*")
re_no_epoch = re.compile(r"^\d*\:")
re_no_revision = re.compile(r"\-[^-]*$")
re_arch_from_filename = re.compile(r"/binary-[^/]+/")
re_extract_src_version = re.compile (r"(\S+)\s*\((.*)\)")

changes_parse_error_exc = "Can't parse line in .changes file";
nk_format_exc = "Unknown Format: in .changes file";
no_files_exc = "No Files: field in .dsc file.";
cant_open_exc = "Can't read file.";
unknown_hostname_exc = "Unknown hostname";
	
######################################################################################

def open_file(filename, mode):
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

def parse_changes(filename):
    changes_in = open_file(filename,'r');
    error = ""
    changes = {};
    lines = changes_in.readlines();
    for line in lines:
        if re.match('^-----BEGIN PGP SIGNATURE', line):
            break;
        if re.match(r'^\s*$|^-----BEGIN PGP SIGNED MESSAGE', line):
            continue;
        slf = re.match(r'^(\S*)\s*:\s*(.*)', line);
        if slf:
            field = string.lower(slf.groups()[0]);
            changes[field] = slf.groups()[1];
            continue;
        mld = re.match(r'^ \.$', line);
        if mld:
            changes[field] = changes[field] + '\n';
            continue;
        mlf = re.match(r'^\s(.*)', line);
        if mlf:
	    changes[field] = changes[field] + mlf.groups()[0] + '\n';
            continue;
	error = error + line;
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
	raise nk_format_exc, changes["format"];

    # No really, this has happened.  Think 0 length .dsc file.
    if not changes.has_key("files"):
	raise no_files_exc
    
    for i in string.split(changes["files"], "\n"):
        if i == "":
            break
        s = string.split(i)
        section = priority = component = ""
        if dsc != "":
            (md5, size, name) = s
        else:
            (md5, size, section, priority, name) = s

        if section == "": section = "-"
        if priority == "": priority = "-"

        if string.find(section, '/') != -1: 
	    component = string.split(section, '/')[0]
	if string.lower(component) == "non-us":
	    component = string.split(section, '/')[0]+ '/' + string.split(section, '/')[1]

        if component == "":
            component = "main"

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
    m = re.match(r"^\s*(\S.*\S)\s*\<([^\> \t]+)\>", maintainer)
    rfc822 = maintainer
    name = ""
    email = ""
    if m != None and len(m.groups()) == 2:
        name = m.group(1)
        email = m.group(2)
        if re.search(r'[,.]', name) != None:
            rfc822 = re.sub(r"^\s*(\S.*\S)\s*\<([^\> \t]+)\>", r"\2 (\1)", maintainer)
    return (rfc822, name, email)

######################################################################################

# sendmail wrapper, takes _either_ a message string or a file as arguments
def send_mail (message, filename):
	#### FIXME, how do I get this out of Cnf in katie?
	sendmail_command = "/usr/sbin/sendmail -oi -t";

	# Sanity check arguments
	if message != "" and filename != "":
		sys.stderr.write ("send_mail() can't be called with both arguments as non-null! (`%s' and `%s')\n%s" % (message, filename))
		sys.exit(1)
	# If we've been passed a string dump it into a temporary file
	if message != "":
		filename = tempfile.mktemp()
		fd = os.open(filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0700)
		os.write (fd, message)
		os.close (fd)
	# Invoke sendmail
	(result, output) = commands.getstatusoutput("%s < %s" % (sendmail_command, filename))
	if (result != 0):
		sys.stderr.write ("Sendmail invocation (`%s') failed for `%s'!\n%s" % (sendmail_command, filename, output))
		sys.exit(result)
	# Clean up any temporary files
	if message !="":
		os.unlink (filename)

######################################################################################

def poolify (source, component):
    if component != "":
	component = component + '/';
    if source[:3] == "lib":
	return component + source[:4] + '/' + source + '/'
    else:
	return component + source[:1] + '/' + source + '/'

######################################################################################

def move (src, dest):
    if os.path.exists(dest) and stat.S_ISDIR(os.stat(dest)[stat.ST_MODE]):
	dest_dir = dest;
    else:
	dest_dir = os.path.dirname(dest);
    if not os.path.exists(dest_dir):
	umask = os.umask(00000);
	os.makedirs(dest_dir, 02775);
	os.umask(umask);
    #print "Moving %s to %s..." % (src, dest);
    shutil.copy2(src, dest);
    os.chmod(dest, 0664);
    os.unlink(src);

######################################################################################

# FIXME: this is inherently nasty.  Can't put this mapping in a conf
# file because the conf file depends on the archive.. doh.  Maybe an
# archive independent conf file is needed.

def where_am_i ():
    res = socket.gethostbyaddr(socket.gethostname());
    if res[0] == 'pandora.debian.org':
        return 'non-US';
    elif res[1] == 'auric.debian.org':
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

######################################################################################

