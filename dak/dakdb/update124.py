# coding=utf8
"""
Put descriptions into sections table

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2020, Joerg Jaspert <joerg@debian.org>
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

import psycopg2
from daklib.dak_exceptions import DBUpdateError

################################################################################

sections = {
    'admin': {'desc': 'Administration Utilities"', 'longdesc': 'Utilities to administer system resources, manage user accounts, etc.'},
    'cli-mono': {'desc': 'Mono/CLI', 'longdesc': 'Everything about Mono and the Common Language Infrastructure.'},
    'comm': {'desc': 'Communication Programs', 'longdesc': 'Software to use your modem in the old fashioned style.'},
    'database': {'desc': 'Databases', 'longdesc': 'Database Servers and Clients.'},
    'debian-installer': {'desc': 'debian-installer udeb packages', 'longdesc': 'Special packages for building customized debian-installer variants. Do not install them on a normal system!'},
    'debug': {'desc': 'Debug packages', 'longdesc': 'Packages providing debugging information for executables and shared libraries.'},
    'devel': {'desc': 'Development', 'longdesc': 'Development utilities, compilers, development environments, libraries, etc.'},
    'doc': {'desc': 'Documentation', 'longdesc': 'FAQs, HOWTOs and other documents trying to explain everything related to Debian, and software needed to browse documentation (man, info, etc).'},
    'editors': {'desc': 'Editors', 'longdesc': 'Software to edit files. Programming environments.'},
    'education': {'desc': 'Education', 'longdesc': 'Software for learning and teaching'},
    'electronics': {'desc': 'Electronics', 'longdesc': 'Electronics utilities.'},
    'embedded': {'desc': 'Embedded software', 'longdesc': 'Software suitable for use in embedded applications.'},
    'fonts': {'desc': 'Fonts', 'longdesc': 'Font packages.'},
    'games': {'desc': 'Games', 'longdesc': 'Programs to spend a nice time with after all this setting up.'},
    'gnome': {'desc': 'GNOME', 'longdesc': 'The GNOME desktop environment, a powerful, easy to use set of integrated applications.'},
    'gnu-r': {'desc': 'GNU R', 'longdesc': 'Everything about GNU R, a statistical computation and graphics system.'},
    'gnustep': {'desc': 'GNUstep', 'longdesc': 'The GNUstep environment.'},
    'golang': {'desc': 'Go', 'longdesc': 'Go programming language, libraries, and development tools.'},
    'graphics': {'desc': 'Graphics', 'longdesc': 'Editors, viewers, converters... Everything to become/be an artist.'},
    'hamradio': {'desc': 'Ham Radio', 'longdesc': 'Software for ham radio.'},
    'haskell': {'desc': 'Haskell', 'longdesc': 'Everything about Haskell.'},
    'httpd': {'desc': 'Web Servers', 'longdesc': 'Web servers and their modules.'},
    'interpreters': {'desc': 'Interpreters', 'longdesc': 'All kind of interpreters for interpreted languages. Macro processors.'},
    'introspection': {'desc': 'Introspection', 'longdesc': 'Machine readable introspection data for use by development tools.'},
    'java': {'desc': 'Java', 'longdesc': 'Everything about Java.'},
    'javascript': {'desc': 'JavaScript', 'longdesc': 'JavaScript programming language, libraries, and development tools.'},
    'kde': {'desc': 'KDE', 'longdesc': 'The K Desktop Environment, a powerful, easy to use set of integrated applications.'},
    'kernel': {'desc': 'Kernels', 'longdesc': 'Operating System Kernels and related modules.'},
    'libdevel': {'desc': 'Library development', 'longdesc': 'Libraries necessary for developers to write programs that use them.'},
    'libs': {'desc': 'Libraries', 'longdesc': 'Libraries to make other programs work. They provide special features to developers.'},
    'lisp': {'desc': 'Lisp', 'longdesc': 'Everything about Lisp.'},
    'localization': {'desc': 'Language packs', 'longdesc': 'Localization support for big software packages.'},
    'mail': {'desc': 'Mail', 'longdesc': 'Programs to route, read, and compose E-mail messages.'},
    'math': {'desc': 'Mathematics', 'longdesc': 'Math software.'},
    'metapackages': {'desc': 'Meta Packages', 'longdesc': 'Packages that mainly provide dependencies on other packages.'},
    'misc': {'desc': 'Miscellaneous', 'longdesc': "Miscellaneous utilities that didn't fit well anywhere else."},
    'net': {'desc': 'Network', 'longdesc': 'Daemons and clients to connect your system to the world.'},
    'news': {'desc': 'Newsgroups', 'longdesc': 'Software to access Usenet, to set up news servers, etc.'},
    'ocaml': {'desc': 'OCaml', 'longdesc': 'Everything about OCaml, an ML language implementation.'},
    'oldlibs': {'desc': 'Old Libraries', 'longdesc': 'Old versions of libraries, kept for backward compatibility with old applications.'},
    'otherosfs': {'desc': "Other OS's and file systems", 'longdesc': 'Software to run programs compiled for other operating systems, and to use their filesystems.'},
    'perl': {'desc': 'Perl', 'longdesc': 'Everything about Perl, an interpreted scripting language.'},
    'php': {'desc': 'PHP', 'longdesc': 'Everything about PHP.'},
    'python': {'desc': 'Python', 'longdesc': 'Everything about Python, an interpreted, interactive object oriented language.'},
    'raku': {'desc': 'Raku', 'longdesc': 'Everything about Raku, an interpreted scripting language.'},
    'ruby': {'desc': 'Ruby', 'longdesc': 'Everything about Ruby, an interpreted object oriented language.'},
    'rust': {'desc': 'Rust', 'longdesc': 'Rust programming language, library crates, and development tools.'},
    'science': {'desc': 'Science', 'longdesc': 'Basic tools for scientific work'},
    'shells': {'desc': 'Shells', 'longdesc': 'Command shells. Friendly user interfaces for beginners.'},
    'sound': {'desc': 'Sound', 'longdesc': 'Utilities to deal with sound: mixers, players, recorders, CD players, etc.'},
    'tasks': {'desc': 'Tasks', 'longdesc': "Packages that are used by 'tasksel', a simple interface for users who want to configure their system to perform a specific task."},
    'tex': {'desc': 'TeX', 'longdesc': 'The famous typesetting software and related programs.'},
    'text': {'desc': 'Text Processing', 'longdesc': 'Utilities to format and print text documents.'},
    'utils': {'desc': 'Utilities', 'longdesc': 'Utilities for file/disk manipulation, backup and archive tools, system monitoring, input systems, etc.'},
    'vcs': {'desc': 'Version Control Systems', 'longdesc': 'Version control systems and related utilities.'},
    'video': {'desc': 'Video', 'longdesc': 'Video viewers, editors, recording, streaming.'},
    'web': {'desc': 'Web Software', 'longdesc': 'Web servers, browsers, proxies, download tools etc.'},
    'x11': {'desc': 'X Window System software', 'longdesc': 'X servers, libraries, window managers, terminal emulators and many related applications.'},
    'xfce': {'desc': 'Xfce', 'longdesc': 'Xfce, a fast and lightweight Desktop Environment.'},
    'zope': {'desc': 'Zope/Plone Framework', 'longdesc': 'Zope Application Server and Plone Content Managment System.'},
}


def do_update(self):
    """
    Update default settings for suites
    """
    print(__doc__)
    try:
        c = self.db.cursor()

        c.execute("""
          ALTER TABLE section
            ADD COLUMN description TEXT NOT NULL DEFAULT 'Missing shortdesc',
            ADD COLUMN longdesc TEXT NOT NULL DEFAULT 'Missing longdesc'
        """)

        for section in sections:
            c.execute("UPDATE section SET description=%s, longdesc=%s WHERE section=%s", (section, sections[section]["desc"], sections[section]["longdesc"]))
            c.execute("UPDATE section SET description=%s, longdesc=%s WHERE section=CONCAT('contrib/', %s)", (section, sections[section]["desc"], sections[section]["longdesc"]))
            c.execute("UPDATE section SET description=%s, longdesc=%s WHERE section=CONCAT('non-free/', %s)", (section, sections[section]["desc"], sections[section]["longdesc"]))

        c.execute("UPDATE config SET value = '124' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 124, rollback issued. Error message : %s' % (str(msg)))
