# vim:set et sw=4:

"""
Central repository of regexes for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
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

###############################################################################

import re

#: Is it a number?
re_isanum = re.compile(r"^\d+$")

#: Looking for the default reply
re_default_answer = re.compile(r"\[(.*)\]")
#: Detect a binnmu
re_bin_only_nmu = re.compile(r"\+b\d+$")

#: To sort out comment lines
re_comments = re.compile(r"\#.*")
#: To ignore comment and whitespace lines.
re_whitespace_comment = re.compile(r"^\s*(#|$)")
re_no_epoch = re.compile(r"^\d+\:")
re_extract_src_version = re.compile(r"(\S+)\s*\((.*)\)")
re_isadeb = re.compile(r"(.+?)_(.+?)_(.+)\.u?deb$")

orig_source_ext_re = r"orig(?:-[a-zA-Z0-9-]+)?\.tar\.(?:gz|bz2|xz)(?:\.asc)?"
file_source_ext_re = "(" + orig_source_ext_re + r"|(?:debian\.)?tar\.(?:gz|bz2|xz)|diff\.gz)"
re_source_ext = re.compile("(" + file_source_ext_re + r"|dsc)$")
re_issource = re.compile(r"(.+)_(.+?)\." + re_source_ext.pattern)

re_single_line_field = re.compile(r"^(\S*?)\s*:\s*(.*)")
re_multi_line_field = re.compile(r"^\s(.*)")
re_taint_free = re.compile(r"^[-+~/\.\w]+$")

re_parse_maintainer = re.compile(r"^\s*(\S.*\S)\s*\<([^\>]+)\>")

re_srchasver = re.compile(r"^(\S+)\s+\((\S+)\)$")
re_verwithext = re.compile(r"^(\d+)(?:\.(\d+))(?:\s+\((\S+)\))?$")

# From clean_proposed_updates.py
re_isdeb = re.compile(r"^(.+)_(.+?)_(.+?).u?deb$")

# From examine_package.py
re_package = re.compile(r"^(.+?)_.*")
re_doc_directory = re.compile(r".*/doc/([^/]*).*")

re_contrib = re.compile('^contrib/')
re_nonfree = re.compile('^non-free/')

re_localhost = re.compile(r"localhost\.localdomain")
re_version = re.compile(r'^(.*)\((.*)\)')

re_newlinespace = re.compile('\n')
re_spacestrip = re.compile(r'(\s)')

# From new_security_install.py
re_taint_free = re.compile(r"^['/;\-\+\.~\s\w]+$")

# From process_unchecked.py
re_changelog_versions = re.compile(r"^\w[-+0-9a-z.]+ \([^\(\) \t]+\)")

# From dak/rm.py
re_strip_source_version = re.compile(r'\s+.*$')
re_build_dep_arch = re.compile(r"\[[^]]+\]")

# From dak/transitions.py
re_broken_package = re.compile(r"[a-zA-Z]\w+\s+\-.*")

# From dak/add_user.py
re_gpg_fingerprint_colon = re.compile(r"^fpr:+(.*):$", re.MULTILINE)
# The next one is dirty
re_user_address = re.compile(r"^pub:.*<(.*)@.*>.*$", re.MULTILINE)
re_user_mails = re.compile(r"^(pub|uid):[^rdin].*<(.*@.*)>.*$", re.MULTILINE)
re_user_name = re.compile(r"^pub:.*:(.*)<.*$", re.MULTILINE)
re_re_mark = re.compile(r'^RE:')

re_parse_lintian = re.compile(r"^(?P<level>W|E|O): (?P<package>.*?): (?P<tag>[^ ]*) ?(?P<description>.*)$")

# in generate-releases
re_gensubrelease = re.compile(r".*/(binary-[0-9a-z-]+|source)$")
re_includeinrelease_byhash = re.compile(r"(Translation-[a-zA-Z_]+\.(?:bz2|xz)|Contents-[0-9a-z-]+.gz|Index|Packages(.gz|.bz2|.xz)?|Sources(.gz|.bz2|.xz)?|Components-[0-9a-z-]+.yml(.gz|.xz)|icons-[0-9x-]+.tar(.gz|.xz)|Release)$")
re_includeinrelease_plain = re.compile(r"(MD5SUMS|SHA256SUMS)$")

# in generate_index_diffs
re_includeinpdiff = re.compile(r"(Translation-[a-zA-Z_]+\.(?:bz2|xz))")


######################################################################
# Patterns matching filenames                                        #
######################################################################

# Match safe filenames
re_file_safe = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.~+-]*$')

# Match safe filenames, including slashes
re_file_safe_slash = re.compile(r'^[a-zA-Z0-9][/a-zA-Z0-9_.~+-]*$')

# Prefix of binary and source filenames
_re_file_prefix = r'^(?P<package>[a-z0-9][a-z0-9.+-]+)_(?P<version>[A-Za-z0-9.~+-]+?)'

# Match binary packages
# Groups: package, version, architecture, type
re_file_binary = re.compile(_re_file_prefix + r'_(?P<architecture>[a-z0-9-]+)\.(?P<type>u?deb)$')

# Match changes files
# Groups: package, version, suffix
re_file_changes = re.compile(_re_file_prefix + r'_(?P<suffix>[a-zA-Z0-9+-]+)\.changes$')

# Match dsc files
# Groups: package, version
re_file_dsc = re.compile(_re_file_prefix + r'\.dsc$')

# Match other source files
# Groups: package, version
re_file_source = re.compile(_re_file_prefix + r'\.' + file_source_ext_re)

# Match upstream tarball
# Groups: package, version
re_file_orig = re.compile(_re_file_prefix + r'\.' + orig_source_ext_re)

# Match buildinfo file
# Groups: package, version, suffix
re_file_buildinfo = re.compile(_re_file_prefix + r'_(?P<suffix>[a-zA-Z0-9+-]+)\.buildinfo$')

######################################################################
# Patterns matching fields                                           #
######################################################################

# Match package name
re_field_package = re.compile(r'^[a-z0-9][a-z0-9.+-]+$')

# Match version
# Groups: without-epoch
re_field_version = re.compile(r'^(?:[0-9]+:)?(?P<without_epoch>[A-Za-z0-9.:~+-]+)$')

# Extract upstream version
# Groups: upstream
re_field_version_upstream = re.compile(r'^(?:[0-9]+:)?(?P<upstream>.*)-[^-]*$')

# Match source field
# Groups: package, version
re_field_source = re.compile(r'^(?P<package>[a-z0-9][a-z0-9.+-]+)(?:\s*\((?P<version>[A-Za-z0-9.:~+-]+)\))?$')
