#!/usr/bin/python

#  bts -- manage bugs filed against ftp.debian.org
#
#  Copyright 2009 Mike O'Connor <stew@vireo.org>
#
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

def usage():
    print """
SYNOPSIS
    dak bts-categorize [options] command

COMMANDS
    list-categories
        List the currently defind categorizations for bugs

    categorize
        Find the bugs filed against ftp.debian.org which have no usertag
        and see if we can categorize the bug by adding a usertag by matching
        the subject against a list of regexps.

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

import sys
import re
import logging
log = logging.getLogger()

import apt_pkg
from daklib import utils
from btsutils.debbugs import debbugs

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

    classifiers = { rm_re: 'remove',
                    dak_re: 'dak',
                    arch_re: 'archs'}

    def __init__( self ):
        self.bts = debbugs()
        self.bts.setUsers(['ftp.debian.org@packages.debian.org'])


    def unclassified_bugs(self):
        """
        Returns a list of open bugs which have not yet been classified
        by one of our usertags.
        """
        return [ bug for bug in self.bts.query("pkg:ftp.debian.org") \
                     if bug.status=='pending' and not bug.usertags ]


    def classify_bug(self, bug):
        """
        if any of our classifiers match, return a newline terminated
        command to set an appropriate usertag, otherwise return an
        empty string
        """
        retval = ""

        for classifier in self.classifiers.keys():
            if classifier.match(bug.summary):
                retval = "usertag %s %s\n" % (bug.bug,
                                            self.classifiers[classifier])
                break

        if retval:
            log.info(retval)
        else:
            log.debug("Unmatched: [%s] %s" % (bug.bug, bug.summary))

        return retval

    def email_text(self):
        controls = ""

        bc = BugClassifier()
        for bug in bc.unclassified_bugs():
            controls += bc.classify_bug(bug)

        if controls:
            return 'user ftp.debian.org@packages.debian.org\n' + controls

import smtplib
import email.Message

def send_email(body):
    to = 'control@bugs.debian.org'
    sender = 'ak@ries.debian.org'
    message = email.Message.Message()
    message["To"] = to
    message["From"] = sender
    message.set_payload(body)
    mailServer = smtplib.SMTP('localhost')
    mailServer.sendmail(sender, to, message.as_string())
    mailServer.quit()

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

    packages = apt_pkg.ParseCommandLine(Cnf, arguments, sys.argv)
    Options = Cnf.SubTree('BtsCategorize::Options')

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
        if Options["Simulate"]:
            print body
        else:
            send_email(body)

    else:
        log.info( "nothing to do" )


if __name__ == '__main__':
#    import doctest
#    doctest.testmod()
    main()
