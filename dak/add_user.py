#!/usr/bin/env python

"""
Add a user to to the uid/maintainer/fingerprint table and
add his key to the GPGKeyring

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2004, 2009  Joerg Jaspert <joerg@ganneff.de>
@license: GNU General Public License version 2 or later
"""

################################################################################
# <elmo> wow, sounds like it'll be a big step up.. configuring dak on a
#        new machine even scares me :)
################################################################################

# You don't want to read this script if you know python.
# I know what I say. I dont know python and I wrote it. So go and read some other stuff.

import commands
import sys
import apt_pkg

from daklib import utils
from daklib.dbconn import DBConn, get_or_set_uid, get_active_keyring_paths
from daklib.regexes import re_gpg_fingerprint_colon, re_user_address, re_user_mails, re_user_name

################################################################################

Cnf = None
Logger = None

################################################################################

def usage(exit_code=0):
    print """Usage: add-user [OPTION]...
Adds a new user to the dak databases and keyrings

    -k, --key                keyid of the User
    -u, --user               userid of the User
    -h, --help               show this help and exit."""
    sys.exit(exit_code)

################################################################################

def main():
    global Cnf
    keyrings = None

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Add-User::Options::Help"),
                 ('k',"key","Add-User::Options::Key", "HasArg"),
                 ('u',"user","Add-User::Options::User", "HasArg"),
                 ]

    for i in [ "help" ]:
        if not Cnf.has_key("Add-User::Options::%s" % (i)):
            Cnf["Add-User::Options::%s" % (i)] = ""

    apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)

    Options = Cnf.subtree("Add-User::Options")
    if Options["help"]:
        usage()

    session = DBConn().session()

    if not keyrings:
        keyrings = get_active_keyring_paths()

    cmd = "gpg --with-colons --no-secmem-warning --no-auto-check-trustdb --no-default-keyring %s --with-fingerprint --list-key %s" \
           % (utils.gpg_keyring_args(keyrings),
              Cnf["Add-User::Options::Key"])
    (result, output) = commands.getstatusoutput(cmd)
    m = re_gpg_fingerprint_colon.search(output)
    if not m:
        print output
        utils.fubar("0x%s: (1) No fingerprint found in gpg output but it returned 0?\n%s" \
                                        % (Cnf["Add-User::Options::Key"], utils.prefix_multi_line_string(output, \
                                                                                                                                                                " [GPG output:] ")))
    primary_key = m.group(1)
    primary_key = primary_key.replace(" ","")

    uid = ""
    if Cnf.has_key("Add-User::Options::User") and Cnf["Add-User::Options::User"]:
        uid = Cnf["Add-User::Options::User"]
        name = Cnf["Add-User::Options::User"]
    else:
        u = re_user_address.search(output)
        if not u:
            print output
            utils.fubar("0x%s: (2) No userid found in gpg output but it returned 0?\n%s" \
                        % (Cnf["Add-User::Options::Key"], utils.prefix_multi_line_string(output, " [GPG output:] ")))
        uid = u.group(1)
        n = re_user_name.search(output)
        name = n.group(1)

# Look for all email addresses on the key.
    emails=[]
    for line in output.split('\n'):
        e = re_user_mails.search(line)
        if not e:
            continue
        emails.append(e.group(2))

    print "0x%s -> %s <%s> -> %s -> %s" % (Cnf["Add-User::Options::Key"], name, emails[0], uid, primary_key)

    prompt = "Add user %s with above data (y/N) ? " % (uid)
    yn = utils.our_raw_input(prompt).lower()

    if yn == "y":
        # Create an account for the user?
        summary = ""

        # Now add user to the database.
        # Note that we provide a session, so we're responsible for committing
        uidobj = get_or_set_uid(uid, session=session)
        uid_id = uidobj.uid_id
        session.commit()

        # Lets add user to the email-whitelist file if its configured.
        if Cnf.has_key("Dinstall::MailWhiteList") and Cnf["Dinstall::MailWhiteList"] != "":
            f = utils.open_file(Cnf["Dinstall::MailWhiteList"], "a")
            for mail in emails:
                f.write(mail+'\n')
            f.close()

        print "Added:\nUid:\t %s (ID: %s)\nMaint:\t %s\nFP:\t %s" % (uid, uid_id, \
                     name, primary_key)

        # Should we send mail to the newly added user?
        if Cnf.find_b("Add-User::SendEmail"):
            mail = name + "<" + emails[0] +">"
            Subst = {}
            Subst["__NEW_MAINTAINER__"] = mail
            Subst["__UID__"] = uid
            Subst["__KEYID__"] = Cnf["Add-User::Options::Key"]
            Subst["__PRIMARY_KEY__"] = primary_key
            Subst["__FROM_ADDRESS__"] = Cnf["Dinstall::MyEmailAddress"]
            Subst["__ADMIN_ADDRESS__"] = Cnf["Dinstall::MyAdminAddress"]
            Subst["__HOSTNAME__"] = Cnf["Dinstall::MyHost"]
            Subst["__DISTRO__"] = Cnf["Dinstall::MyDistribution"]
            Subst["__SUMMARY__"] = summary
            new_add_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/add-user.added")
            utils.send_mail(new_add_message)

    else:
        uid = None

#######################################################################################

if __name__ == '__main__':
    main()
