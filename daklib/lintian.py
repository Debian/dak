#!/usr/bin/python

""" Utility functions for lintian checks in dak

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Chris Lamb <lamby@debian.org>
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

# <mhy> I often wonder if we should use NSA bot or something instead and get dinstall
#       to send emails telling us about its progress :-)
# <mhy> dinstall: I'm processing openoffice
# <mhy> dinstall: I'm choking, please help me
# <Ganneff> yeah. get floods in here, for 600 accepted packages.
# <mhy> hehe
# <Ganneff> im not sure the other opers will like it if i oper up the bot, just so it
#           can flood faster
# <mhy> flood all debian related channels
# <mhy> just to be safe
# <Ganneff> /msg #debian-* dinstall: starting
# <Ganneff> more interesting would be the first message in #debian, the next in
#           #d-devel, then #d-qa
# <Ganneff> and expect people to monitor all.
# <Ganneff> i bet we have enough debian channels to at least put the timestamps in
#           seperate channels each
# <Ganneff> and if not  -  we can make it go multi-network
# <Ganneff> first oftc, then opn, then ircnet, then - we will find some. quakenet anyone?
# <mhy> I should know better than to give you ideas

################################################################################

from regexes import re_parse_lintian

def parse_lintian_output(output):
    """
    Parses Lintian output and returns a generator with the data.

    >>> list(parse_lintian_output('W: pkgname: some-tag path/to/file'))
    [('W', 'pkgname', 'some-tag', 'path/to/file')]

    @type output: string
    @param output: The output from lintian
    """

    for line in output.split('\n'):
        m = re_parse_lintian.match(line)
        if m:
            yield m.groupdict()

def generate_reject_messages(parsed_tags, tag_definitions, log=lambda *args: args):
    """
    Generates package reject messages by comparing parsed lintian output with
    tag definitions. Returns a generator containing the reject messages.

    @param parsed_tags: Parsed lintian tags as returned by L{parse_lintian_output}

    @param tag_definitions: YAML.load lintian tag definitions to reject on

    @return: Reject message(s), if any
    """

    tags = set()
    for values in tag_definitions.values():
        for tag_name in values:
            tags.add(tag_name)

    for tag in parsed_tags:
        tag_name = tag['tag']

        if tag_name not in tags:
            continue

        # Was tag overridden?
        if tag['level'] == 'O':

            if tag_name in tag_definitions['nonfatal']:
                # Overriding this tag is allowed.
                pass

            elif tag_name in tag_definitions['fatal']:
                # Overriding this tag is NOT allowed.

                log('ftpmaster does not allow tag to be overridable', tag_name)
                yield "%(package)s: Overriden tag %(tag)s found, but this " \
                    "tag may not be overridden." % tag

        else:
            # Tag is known and not overridden; reject
            yield "%(package)s: lintian output: '%(tag)s %(description)s', " \
                "automatically rejected package." % tag

            # Now tell if they *might* override it.
            if tag_name in tag_definitions['nonfatal']:
                log("auto rejecting", "overridable", tag_name)
                yield "%(package)s: If you have a good reason, you may " \
                   "override this lintian tag." % tag
            else:
                log("auto rejecting", "not overridable", tag_name)
