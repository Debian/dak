#!/usr/bin/python

"""
bts -- manage bugs filed against ftp.debian.org

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009 Mike O'Connor <stew@vireo.org>
@copyright: 2010 Alexander Reichle-Schmehl <tolimar@debian.org>
@license: GNU General Public License version 2 or later
"""

#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 2, or (at your option) any
#  later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
#  USA.

################################################################################
################################################################################

import sys
import re
import logging
log = logging.getLogger()

import apt_pkg
from daklib import utils
import debianbts as bts

def usage():
    print """
SYNOPSIS
    dak bts-categorize [options]

OPTIONS
    -s
    --simulate
        Don't send email, instead output the lines that would be sent to
        control@b.d.o.

    -v
    --verbose
        Print more informational log messages

    -q
    --quiet
        Suppress informational messages

    -h
    --help
        Print this documentation.
"""

arguments = [('s','simulate','BtsCategorize::Options::Simulate'),
             ('v', 'verbose', 'BtsCategorize::Options::Verbose'),
             ('q', 'quiet', 'BtsCategorize::Options::Quiet'),
             ('h', 'help', 'BtsCategorize::Options::Help')]

class BugClassifier(object):
    """
    classify bugs using usertags based on the bug subject lines

    >>> BugClassifier.rm_re.match( "RM: asdf" ) != None
    True
    >>> BugClassifier.rm_re.match( "[dak] Packages.diff/Index broken" ) != None
    False
    >>> BugClassifier.dak_re.match( "[dak] Packages.diff/Index broken" ) != None
    True
    """
    rm_re = re.compile( "^RM" )
    dak_re = re.compile( "^\[dak\]" )
    arch_re = re.compile( "^\[Architectures\]" )
    override_re = re.compile( "^override" )

    classifiers = { rm_re: 'remove',
                    dak_re: 'dak',
                    arch_re: 'archs',
                    override_re: 'override'}

    def unclassified_bugs(self):
        """
        Returns a list of open bugs which have not yet been classified
        by one of our usertags.
        """

	tagged_bugs = bts.get_usertag('ftp.debian.org@packages.debian.org')
	tagged_bugs_ftp = []
	for tags in tagged_bugs.keys():
		tagged_bugs_ftp += tagged_bugs[tags]

        return [ bug for bug in bts.get_status( bts.get_bugs("package", "ftp.debian.org" ) ) \
                     if bug.pending=='pending' and not bug.bug_num in tagged_bugs_ftp ]


    def classify_bug(self, bug):
        """
        if any of our classifiers match, return a newline terminated
        command to set an appropriate usertag, otherwise return an
        empty string
        """
        retval = ""

        for classifier in self.classifiers.keys():
            if classifier.match(bug.subject):
                retval = "usertag %s %s\n" % (bug.bug_num,
                                            self.classifiers[classifier])
                break

        if retval:
            log.info(retval)
        else:
            log.debug("Unmatched: [%s] %s" % (bug.bug_num, bug.subject))

        return retval

    def email_text(self):
        controls = ""

        bc = BugClassifier()
        try:
            for bug in bc.unclassified_bugs():
                controls += bc.classify_bug(bug)

            return controls
        except:
            log.error("couldn't retrieve bugs from soap interface: %s" % sys.exc_info()[0])
            return None

def send_email(commands, simulate=False):
    global Cnf

    Subst = {'__COMMANDS__' : commands,
             "__DAK_ADDRESS__": Cnf["Dinstall::MyAdminAddress"]}

    bts_mail_message = utils.TemplateSubst(
        Subst,Cnf["Dir::Templates"]+"/bts-categorize")

    if simulate:
        print bts_mail_message
    else:
        utils.send_mail( bts_mail_message )

def main():
    """
    for now, we just dump a list of commands that could be sent for
    control@b.d.o
    """
    global Cnf
    Cnf = utils.get_conf()

    for arg in arguments:
        opt = "BtsCategorize::Options::%s" % arg[1]
        if not Cnf.has_key(opt):
            Cnf[opt] = ""

    packages = apt_pkg.parse_commandline(Cnf, arguments, sys.argv)
    Options = Cnf.subtree('BtsCategorize::Options')

    if Options["Help"]:
        usage()
        sys.exit( 0 )

    if Options["Quiet"]:
        level=logging.ERROR

    elif Options["Verbose"]:
        level=logging.DEBUG

    else:
        level=logging.INFO

    logging.basicConfig( level=level,
                         format='%(asctime)s %(levelname)s %(message)s',
                         stream = sys.stderr )

    body = BugClassifier().email_text()

    if body:
        send_email(body, Options["Simulate"])

    else:
        log.info( "nothing to do" )


if __name__ == '__main__':
#    import doctest
#    doctest.testmod()
    main()
