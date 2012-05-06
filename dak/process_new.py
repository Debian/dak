#!/usr/bin/env python
# vim:set et ts=4 sw=4:

""" Handles NEW and BYHAND packages

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009 Joerg Jaspert <joerg@debian.org>
@copyright: 2009 Frank Lichtenheld <djpig@debian.org>
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

# 23:12|<aj> I will not hush!
# 23:12|<elmo> :>
# 23:12|<aj> Where there is injustice in the world, I shall be there!
# 23:13|<aj> I shall not be silenced!
# 23:13|<aj> The world shall know!
# 23:13|<aj> The world *must* know!
# 23:13|<elmo> oh dear, he's gone back to powerpuff girls... ;-)
# 23:13|<aj> yay powerpuff girls!!
# 23:13|<aj> buttercup's my favourite, who's yours?
# 23:14|<aj> you're backing away from the keyboard right now aren't you?
# 23:14|<aj> *AREN'T YOU*?!
# 23:15|<aj> I will not be treated like this.
# 23:15|<aj> I shall have my revenge.
# 23:15|<aj> I SHALL!!!

################################################################################

import copy
import errno
import os
import readline
import stat
import sys
import time
import contextlib
import pwd
import apt_pkg, apt_inst
import examine_package

from daklib.dbconn import *
from daklib.queue import *
from daklib import daklog
from daklib import utils
from daklib.regexes import re_no_epoch, re_default_answer, re_isanum, re_package
from daklib.dak_exceptions import CantOpenError, AlreadyLockedError, CantGetLockError
from daklib.summarystats import SummaryStats
from daklib.config import Config
from daklib.changesutils import *

# Globals
Options = None
Logger = None

Priorities = None
Sections = None

################################################################################
################################################################################
################################################################################

def recheck(upload, session):
# STU: I'm not sure, but I don't thin kthis is necessary any longer:    upload.recheck(session)
    if len(upload.rejects) > 0:
        answer = "XXX"
        if Options["No-Action"] or Options["Automatic"] or Options["Trainee"]:
            answer = 'S'

        print "REJECT\n%s" % '\n'.join(upload.rejects)
        prompt = "[R]eject, Skip, Quit ?"

        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.match(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'R':
            upload.do_reject(manual=0, reject_message='\n'.join(upload.rejects))
            upload.pkg.remove_known_changes(session=session)
            session.commit()
            return 0
        elif answer == 'S':
            return 0
        elif answer == 'Q':
            end()
            sys.exit(0)

    return 1

################################################################################

class Section_Completer:
    def __init__ (self, session):
        self.sections = []
        self.matches = []
        for s, in session.query(Section.section):
            self.sections.append(s)

    def complete(self, text, state):
        if state == 0:
            self.matches = []
            n = len(text)
            for word in self.sections:
                if word[:n] == text:
                    self.matches.append(word)
        try:
            return self.matches[state]
        except IndexError:
            return None

############################################################

class Priority_Completer:
    def __init__ (self, session):
        self.priorities = []
        self.matches = []
        for p, in session.query(Priority.priority):
            self.priorities.append(p)

    def complete(self, text, state):
        if state == 0:
            self.matches = []
            n = len(text)
            for word in self.priorities:
                if word[:n] == text:
                    self.matches.append(word)
        try:
            return self.matches[state]
        except IndexError:
            return None

################################################################################

def print_new (new, upload, indexed, file=sys.stdout):
    check_valid(new)
    broken = False
    index = 0
    for pkg in new.keys():
        index += 1
        section = new[pkg]["section"]
        priority = new[pkg]["priority"]
        if new[pkg]["section id"] == -1:
            section += "[!]"
            broken = True
        if new[pkg]["priority id"] == -1:
            priority += "[!]"
            broken = True
        if indexed:
            line = "(%s): %-20s %-20s %-20s" % (index, pkg, priority, section)
        else:
            line = "%-20s %-20s %-20s" % (pkg, priority, section)
        line = line.strip()+'\n'
        file.write(line)
    notes = get_new_comments(upload.pkg.changes.get("source"))
    for note in notes:
        print "\nAuthor: %s\nVersion: %s\nTimestamp: %s\n\n%s" \
              % (note.author, note.version, note.notedate, note.comment)
        print "-" * 72
    return broken, len(notes) > 0

################################################################################

def index_range (index):
    if index == 1:
        return "1"
    else:
        return "1-%s" % (index)

################################################################################
################################################################################

def edit_new (new, upload):
    # Write the current data to a temporary file
    (fd, temp_filename) = utils.temp_filename()
    temp_file = os.fdopen(fd, 'w')
    print_new (new, upload, indexed=0, file=temp_file)
    temp_file.close()
    # Spawn an editor on that file
    editor = os.environ.get("EDITOR","vi")
    result = os.system("%s %s" % (editor, temp_filename))
    if result != 0:
        utils.fubar ("%s invocation failed for %s." % (editor, temp_filename), result)
    # Read the edited data back in
    temp_file = utils.open_file(temp_filename)
    lines = temp_file.readlines()
    temp_file.close()
    os.unlink(temp_filename)
    # Parse the new data
    for line in lines:
        line = line.strip()
        if line == "":
            continue
        s = line.split()
        # Pad the list if necessary
        s[len(s):3] = [None] * (3-len(s))
        (pkg, priority, section) = s[:3]
        if not new.has_key(pkg):
            utils.warn("Ignoring unknown package '%s'" % (pkg))
        else:
            # Strip off any invalid markers, print_new will readd them.
            if section.endswith("[!]"):
                section = section[:-3]
            if priority.endswith("[!]"):
                priority = priority[:-3]
            for f in new[pkg]["files"]:
                upload.pkg.files[f]["section"] = section
                upload.pkg.files[f]["priority"] = priority
            new[pkg]["section"] = section
            new[pkg]["priority"] = priority

################################################################################

def edit_index (new, upload, index):
    priority = new[index]["priority"]
    section = new[index]["section"]
    ftype = new[index]["type"]
    done = 0
    while not done:
        print "\t".join([index, priority, section])

        answer = "XXX"
        if ftype != "dsc":
            prompt = "[B]oth, Priority, Section, Done ? "
        else:
            prompt = "[S]ection, Done ? "
        edit_priority = edit_section = 0

        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.match(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'P':
            edit_priority = 1
        elif answer == 'S':
            edit_section = 1
        elif answer == 'B':
            edit_priority = edit_section = 1
        elif answer == 'D':
            done = 1

        # Edit the priority
        if edit_priority:
            readline.set_completer(Priorities.complete)
            got_priority = 0
            while not got_priority:
                new_priority = utils.our_raw_input("New priority: ").strip()
                if new_priority not in Priorities.priorities:
                    print "E: '%s' is not a valid priority, try again." % (new_priority)
                else:
                    got_priority = 1
                    priority = new_priority

        # Edit the section
        if edit_section:
            readline.set_completer(Sections.complete)
            got_section = 0
            while not got_section:
                new_section = utils.our_raw_input("New section: ").strip()
                if new_section not in Sections.sections:
                    print "E: '%s' is not a valid section, try again." % (new_section)
                else:
                    got_section = 1
                    section = new_section

        # Reset the readline completer
        readline.set_completer(None)

    for f in new[index]["files"]:
        upload.pkg.files[f]["section"] = section
        upload.pkg.files[f]["priority"] = priority
    new[index]["priority"] = priority
    new[index]["section"] = section
    return new

################################################################################

def edit_overrides (new, upload, session):
    print
    done = 0
    while not done:
        print_new (new, upload, indexed=1)
        new_index = {}
        index = 0
        for i in new.keys():
            index += 1
            new_index[index] = i

        prompt = "(%s) edit override <n>, Editor, Done ? " % (index_range(index))

        got_answer = 0
        while not got_answer:
            answer = utils.our_raw_input(prompt)
            if not answer.isdigit():
                answer = answer[:1].upper()
            if answer == "E" or answer == "D":
                got_answer = 1
            elif re_isanum.match (answer):
                answer = int(answer)
                if (answer < 1) or (answer > index):
                    print "%s is not a valid index (%s).  Please retry." % (answer, index_range(index))
                else:
                    got_answer = 1

        if answer == 'E':
            edit_new(new, upload)
        elif answer == 'D':
            done = 1
        else:
            edit_index (new, upload, new_index[answer])

    return new


################################################################################

def check_pkg (upload):
    save_stdout = sys.stdout
    try:
        sys.stdout = os.popen("less -R -", 'w', 0)
        changes = utils.parse_changes (upload.pkg.changes_file)
        print examine_package.display_changes(changes['distribution'], upload.pkg.changes_file)
        files = upload.pkg.files
        for f in files.keys():
            if files[f].has_key("new"):
                ftype = files[f]["type"]
                if ftype == "deb":
                    print examine_package.check_deb(changes['distribution'], f)
                elif ftype == "dsc":
                    print examine_package.check_dsc(changes['distribution'], f)
        print examine_package.output_package_relations()
    except IOError as e:
        if e.errno == errno.EPIPE:
            utils.warn("[examine_package] Caught EPIPE; skipping.")
        else:
            sys.stdout = save_stdout
            raise
    except KeyboardInterrupt:
        utils.warn("[examine_package] Caught C-c; skipping.")
    sys.stdout = save_stdout

################################################################################

## FIXME: horribly Debian specific

def do_bxa_notification(upload):
    files = upload.pkg.files
    summary = ""
    for f in files.keys():
        if files[f]["type"] == "deb":
            control = apt_pkg.TagSection(utils.deb_extract_control(utils.open_file(f)))
            summary += "\n"
            summary += "Package: %s\n" % (control.find("Package"))
            summary += "Description: %s\n" % (control.find("Description"))
    upload.Subst["__BINARY_DESCRIPTIONS__"] = summary
    bxa_mail = utils.TemplateSubst(upload.Subst,Config()["Dir::Templates"]+"/process-new.bxa_notification")
    utils.send_mail(bxa_mail)

################################################################################

def add_overrides (new, upload, session):
    changes = upload.pkg.changes
    files = upload.pkg.files
    srcpkg = changes.get("source")

    for suite in changes["suite"].keys():
        suite_id = get_suite(suite).suite_id
        for pkg in new.keys():
            component_id = get_component(new[pkg]["component"]).component_id
            type_id = get_override_type(new[pkg]["type"]).overridetype_id
            priority_id = new[pkg]["priority id"]
            section_id = new[pkg]["section id"]
            Logger.log(["%s (%s) overrides" % (pkg, srcpkg), suite, new[pkg]["component"], new[pkg]["type"], new[pkg]["priority"], new[pkg]["section"]])
            session.execute("INSERT INTO override (suite, component, type, package, priority, section, maintainer) VALUES (:sid, :cid, :tid, :pkg, :pid, :sectid, '')",
                            { 'sid': suite_id, 'cid': component_id, 'tid':type_id, 'pkg': pkg, 'pid': priority_id, 'sectid': section_id})
            for f in new[pkg]["files"]:
                if files[f].has_key("new"):
                    del files[f]["new"]
            del new[pkg]

    session.commit()

    if Config().find_b("Dinstall::BXANotify"):
        do_bxa_notification(upload)

################################################################################

def do_new(upload, session):
    print "NEW\n"
    files = upload.pkg.files
    upload.check_files(not Options["No-Action"])
    changes = upload.pkg.changes
    cnf = Config()

    # Check for a valid distribution
    upload.check_distributions()

    # Make a copy of distribution we can happily trample on
    changes["suite"] = copy.copy(changes["distribution"])

    # Try to get an included dsc
    dsc = None
    (status, _) = upload.load_dsc()
    if status:
        dsc = upload.pkg.dsc

    # The main NEW processing loop
    done = 0
    new = {}
    while not done:
        # Find out what's new
        new, byhand = determine_new(upload.pkg.changes_file, changes, files, dsc=dsc, session=session, new=new)

        if not new:
            break

        answer = "XXX"
        if Options["No-Action"] or Options["Automatic"]:
            answer = 'S'

        (broken, note) = print_new(new, upload, indexed=0)
        prompt = ""

        if not broken and not note:
            prompt = "Add overrides, "
        if broken:
            print "W: [!] marked entries must be fixed before package can be processed."
        if note:
            print "W: note must be removed before package can be processed."
            prompt += "RemOve all notes, Remove note, "

        prompt += "Edit overrides, Check, Manual reject, Note edit, Prod, [S]kip, Quit ?"

        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer in ( 'A', 'E', 'M', 'O', 'R' ) and Options["Trainee"]:
            utils.warn("Trainees can't do that")
            continue

        if answer == 'A' and not Options["Trainee"]:
            try:
                check_daily_lock()
                done = add_overrides (new, upload, session)
                new_accept(upload, Options["No-Action"], session)
                Logger.log(["NEW ACCEPT: %s" % (upload.pkg.changes_file)])
            except CantGetLockError:
                print "Hello? Operator! Give me the number for 911!"
                print "Dinstall in the locked area, cant process packages, come back later"
        elif answer == 'C':
            check_pkg(upload)
        elif answer == 'E' and not Options["Trainee"]:
            new = edit_overrides (new, upload, session)
        elif answer == 'M' and not Options["Trainee"]:
            aborted = upload.do_reject(manual=1,
                                       reject_message=Options["Manual-Reject"],
                                       notes=get_new_comments(changes.get("source", ""), session=session))
            if not aborted:
                upload.pkg.remove_known_changes(session=session)
                session.commit()
                Logger.log(["NEW REJECT: %s" % (upload.pkg.changes_file)])
                done = 1
        elif answer == 'N':
            edit_note(get_new_comments(changes.get("source", ""), session=session),
                      upload, session, bool(Options["Trainee"]))
        elif answer == 'P' and not Options["Trainee"]:
            prod_maintainer(get_new_comments(changes.get("source", ""), session=session),
                            upload)
            Logger.log(["NEW PROD: %s" % (upload.pkg.changes_file)])
        elif answer == 'R' and not Options["Trainee"]:
            confirm = utils.our_raw_input("Really clear note (y/N)? ").lower()
            if confirm == "y":
                for c in get_new_comments(changes.get("source", ""), changes.get("version", ""), session=session):
                    session.delete(c)
                session.commit()
        elif answer == 'O' and not Options["Trainee"]:
            confirm = utils.our_raw_input("Really clear all notes (y/N)? ").lower()
            if confirm == "y":
                for c in get_new_comments(changes.get("source", ""), session=session):
                    session.delete(c)
                session.commit()

        elif answer == 'S':
            done = 1
        elif answer == 'Q':
            end()
            sys.exit(0)

################################################################################
################################################################################
################################################################################

def usage (exit_code=0):
    print """Usage: dak process-new [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -b, --no-binaries         do not sort binary-NEW packages first
  -c, --comments            show NEW comments
  -h, --help                show this help and exit.
  -m, --manual-reject=MSG   manual reject with `msg'
  -n, --no-action           don't do anything
  -t, --trainee             FTP Trainee mode
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

################################################################################

def do_byhand(upload, session):
    done = 0
    while not done:
        files = upload.pkg.files
        will_install = True
        byhand = []

        for f in files.keys():
            if files[f]["section"] == "byhand":
                if os.path.exists(f):
                    print "W: %s still present; please process byhand components and try again." % (f)
                    will_install = False
                else:
                    byhand.append(f)

        answer = "XXXX"
        if Options["No-Action"]:
            answer = "S"
        if will_install:
            if Options["Automatic"] and not Options["No-Action"]:
                answer = 'A'
            prompt = "[A]ccept, Manual reject, Skip, Quit ?"
        else:
            prompt = "Manual reject, [S]kip, Quit ?"

        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'A':
            dbchg = get_dbchange(upload.pkg.changes_file, session)
            if dbchg is None:
                print "Warning: cannot find changes file in database; can't process BYHAND"
            else:
                try:
                    check_daily_lock()
                    done = 1
                    for b in byhand:
                        # Find the file entry in the database
                        found = False
                        for f in dbchg.files:
                            if f.filename == b:
                                found = True
                                f.processed = True
                                break

                        if not found:
                            print "Warning: Couldn't find BYHAND item %s in the database to mark it processed" % b

                    session.commit()
                    Logger.log(["BYHAND ACCEPT: %s" % (upload.pkg.changes_file)])
                except CantGetLockError:
                    print "Hello? Operator! Give me the number for 911!"
                    print "Dinstall in the locked area, cant process packages, come back later"
        elif answer == 'M':
            aborted = upload.do_reject(manual=1,
                                       reject_message=Options["Manual-Reject"],
                                       notes=get_new_comments(changes.get("source", ""), session=session))
            if not aborted:
                upload.pkg.remove_known_changes(session=session)
                session.commit()
                Logger.log(["BYHAND REJECT: %s" % (upload.pkg.changes_file)])
                done = 1
        elif answer == 'S':
            done = 1
        elif answer == 'Q':
            end()
            sys.exit(0)

################################################################################

def check_daily_lock():
    """
    Raises CantGetLockError if the dinstall daily.lock exists.
    """

    cnf = Config()
    try:
        lockfile = cnf.get("Process-New::DinstallLockFile",
                           os.path.join(cnf['Dir::Lock'], 'processnew.lock'))

        os.open(lockfile,
                os.O_RDONLY | os.O_CREAT | os.O_EXCL)
    except OSError as e:
        if e.errno == errno.EEXIST or e.errno == errno.EACCES:
            raise CantGetLockError

    os.unlink(lockfile)


@contextlib.contextmanager
def lock_package(package):
    """
    Lock C{package} so that noone else jumps in processing it.

    @type package: string
    @param package: source package name to lock
    """

    cnf = Config()

    path = os.path.join(cnf.get("Process-New::LockDir", cnf['Dir::Lock']), package)

    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDONLY)
    except OSError as e:
        if e.errno == errno.EEXIST or e.errno == errno.EACCES:
            user = pwd.getpwuid(os.stat(path)[stat.ST_UID])[4].split(',')[0].replace('.', '')
            raise AlreadyLockedError(user)

    try:
        yield fd
    finally:
        os.unlink(path)

class clean_holding(object):
    def __init__(self,pkg):
        self.pkg = pkg

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        h = Holding()

        for f in self.pkg.files.keys():
            if os.path.exists(os.path.join(h.holding_dir, f)):
                os.unlink(os.path.join(h.holding_dir, f))


def do_pkg(changes_full_path, session):
    changes_dir = os.path.dirname(changes_full_path)
    changes_file = os.path.basename(changes_full_path)

    u = Upload()
    u.pkg.changes_file = changes_file
    (u.pkg.changes["fingerprint"], rejects) = utils.check_signature(changes_file)
    u.load_changes(changes_file)
    u.pkg.directory = changes_dir
    u.update_subst()
    u.logger = Logger
    origchanges = os.path.abspath(u.pkg.changes_file)

    # Try to get an included dsc
    dsc = None
    (status, _) = u.load_dsc()
    if status:
        dsc = u.pkg.dsc

    cnf = Config()
    bcc = "X-DAK: dak process-new"
    if cnf.has_key("Dinstall::Bcc"):
        u.Subst["__BCC__"] = bcc + "\nBcc: %s" % (cnf["Dinstall::Bcc"])
    else:
        u.Subst["__BCC__"] = bcc

    files = u.pkg.files
    u.check_distributions()
    for deb_filename, f in files.items():
        if deb_filename.endswith(".udeb") or deb_filename.endswith(".deb"):
            u.binary_file_checks(deb_filename, session)
            u.check_binary_against_db(deb_filename, session)
        else:
            u.source_file_checks(deb_filename, session)
            u.check_source_against_db(deb_filename, session)

        u.pkg.changes["suite"] = copy.copy(u.pkg.changes["distribution"])

    try:
        with lock_package(u.pkg.changes["source"]):
            with clean_holding(u.pkg):
                if not recheck(u, session):
                    return

                new, byhand = determine_new(u.pkg.changes_file, u.pkg.changes, files, dsc=dsc, session=session)
                if byhand:
                    do_byhand(u, session)
                elif new:
                    do_new(u, session)
                else:
                    try:
                        check_daily_lock()
                        new_accept(u, Options["No-Action"], session)
                    except CantGetLockError:
                        print "Hello? Operator! Give me the number for 911!"
                        print "Dinstall in the locked area, cant process packages, come back later"

    except AlreadyLockedError as e:
        print "Seems to be locked by %s already, skipping..." % (e)

def show_new_comments(changes_files, session):
    sources = set()
    query = """SELECT package, version, comment, author
               FROM new_comments
               WHERE package IN ('"""

    for changes in changes_files:
        sources.add(os.path.basename(changes).split("_")[0])

    query += "%s') ORDER BY package, version" % "', '".join(sources)
    r = session.execute(query)

    for i in r:
        print "%s_%s\n%s\n(%s)\n\n\n" % (i[0], i[1], i[2], i[3])

    session.commit()

################################################################################

def end():
    accept_count = SummaryStats().accept_count
    accept_bytes = SummaryStats().accept_bytes

    if accept_count:
        sets = "set"
        if accept_count > 1:
            sets = "sets"
        sys.stderr.write("Accepted %d package %s, %s.\n" % (accept_count, sets, utils.size_type(int(accept_bytes))))
        Logger.log(["total",accept_count,accept_bytes])

    if not Options["No-Action"] and not Options["Trainee"]:
        Logger.close()

################################################################################

def main():
    global Options, Logger, Sections, Priorities

    cnf = Config()
    session = DBConn().session()

    Arguments = [('a',"automatic","Process-New::Options::Automatic"),
                 ('b',"no-binaries","Process-New::Options::No-Binaries"),
                 ('c',"comments","Process-New::Options::Comments"),
                 ('h',"help","Process-New::Options::Help"),
                 ('m',"manual-reject","Process-New::Options::Manual-Reject", "HasArg"),
                 ('t',"trainee","Process-New::Options::Trainee"),
                 ('n',"no-action","Process-New::Options::No-Action")]

    for i in ["automatic", "no-binaries", "comments", "help", "manual-reject", "no-action", "version", "trainee"]:
        if not cnf.has_key("Process-New::Options::%s" % (i)):
            cnf["Process-New::Options::%s" % (i)] = ""

    changes_files = apt_pkg.parse_commandline(cnf.Cnf,Arguments,sys.argv)
    if len(changes_files) == 0:
        new_queue = get_policy_queue('new', session );
        changes_paths = [ os.path.join(new_queue.path, j) for j in utils.get_changes_files(new_queue.path) ]
    else:
        changes_paths = [ os.path.abspath(j) for j in changes_files ]

    Options = cnf.subtree("Process-New::Options")

    if Options["Help"]:
        usage()

    if not Options["No-Action"]:
        try:
            Logger = daklog.Logger("process-new")
        except CantOpenError as e:
            Options["Trainee"] = "True"

    Sections = Section_Completer(session)
    Priorities = Priority_Completer(session)
    readline.parse_and_bind("tab: complete")

    if len(changes_paths) > 1:
        sys.stderr.write("Sorting changes...\n")
    changes_files = sort_changes(changes_paths, session, Options["No-Binaries"])

    if Options["Comments"]:
        show_new_comments(changes_files, session)
    else:
        for changes_file in changes_files:
            changes_file = utils.validate_changes_file_arg(changes_file, 0)
            if not changes_file:
                continue
            print "\n" + os.path.basename(changes_file)

            do_pkg (changes_file, session)

    end()

################################################################################

if __name__ == '__main__':
    main()
