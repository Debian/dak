#!/usr/bin/env python

# Handles NEW and BYHAND packages
# Copyright (C) 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>

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

import copy, errno, os, readline, stat, sys, time
import apt_pkg, apt_inst
import examine_package
import daklib.database
import daklib.logging
import daklib.queue 
import daklib.utils

# Globals
Cnf = None
Options = None
Upload = None
projectB = None
Logger = None

Priorities = None
Sections = None

reject_message = ""

################################################################################
################################################################################
################################################################################

def reject (str, prefix="Rejected: "):
    global reject_message
    if str:
        reject_message += prefix + str + "\n"

def recheck():
    global reject_message
    files = Upload.pkg.files
    reject_message = ""

    for file in files.keys():
        # The .orig.tar.gz can disappear out from under us is it's a
        # duplicate of one in the archive.
        if not files.has_key(file):
            continue
        # Check that the source still exists
        if files[file]["type"] == "deb":
            source_version = files[file]["source version"]
            source_package = files[file]["source package"]
            if not Upload.pkg.changes["architecture"].has_key("source") \
               and not Upload.source_exists(source_package, source_version, Upload.pkg.changes["distribution"].keys()):
                source_epochless_version = daklib.utils.re_no_epoch.sub('', source_version)
                dsc_filename = "%s_%s.dsc" % (source_package, source_epochless_version)
                if not os.path.exists(Cnf["Dir::Queue::Accepted"] + '/' + dsc_filename):
                    reject("no source found for %s %s (%s)." % (source_package, source_version, file))

        # Version and file overwrite checks
        if files[file]["type"] == "deb":
            reject(Upload.check_binary_against_db(file))
        elif files[file]["type"] == "dsc":
            reject(Upload.check_source_against_db(file))
            (reject_msg, is_in_incoming) = Upload.check_dsc_against_db(file)
            reject(reject_msg)

    if reject_message:
        answer = "XXX"
        if Options["No-Action"] or Options["Automatic"]:
            answer = 'S'

        print "REJECT\n" + reject_message,
        prompt = "[R]eject, Skip, Quit ?"

        while prompt.find(answer) == -1:
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.match(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'R':
            Upload.do_reject(0, reject_message)
            os.unlink(Upload.pkg.changes_file[:-8]+".dak")
            return 0
        elif answer == 'S':
            return 0
        elif answer == 'Q':
            sys.exit(0)

    return 1

################################################################################

def determine_new (changes, files):
    new = {}

    # Build up a list of potentially new things
    for file in files.keys():
        f = files[file]
        # Skip byhand elements
        if f["type"] == "byhand":
            continue
        pkg = f["package"]
        priority = f["priority"]
        section = f["section"]
        # FIXME: unhardcode
        if section == "non-US/main":
            section = "non-US"
        type = get_type(f)
        component = f["component"]

        if type == "dsc":
            priority = "source"
        if not new.has_key(pkg):
            new[pkg] = {}
            new[pkg]["priority"] = priority
            new[pkg]["section"] = section
            new[pkg]["type"] = type
            new[pkg]["component"] = component
            new[pkg]["files"] = []
        else:
            old_type = new[pkg]["type"]
            if old_type != type:
                # source gets trumped by deb or udeb
                if old_type == "dsc":
                    new[pkg]["priority"] = priority
                    new[pkg]["section"] = section
                    new[pkg]["type"] = type
                    new[pkg]["component"] = component
        new[pkg]["files"].append(file)
        if f.has_key("othercomponents"):
            new[pkg]["othercomponents"] = f["othercomponents"]

    for suite in changes["suite"].keys():
        suite_id = daklib.database.get_suite_id(suite)
        for pkg in new.keys():
            component_id = daklib.database.get_component_id(new[pkg]["component"])
            type_id = daklib.database.get_override_type_id(new[pkg]["type"])
            q = projectB.query("SELECT package FROM override WHERE package = '%s' AND suite = %s AND component = %s AND type = %s" % (pkg, suite_id, component_id, type_id))
            ql = q.getresult()
            if ql:
                for file in new[pkg]["files"]:
                    if files[file].has_key("new"):
                        del files[file]["new"]
                del new[pkg]

    if changes["suite"].has_key("stable"):
        print "WARNING: overrides will be added for stable!"
    if changes["suite"].has_key("oldstable"):
        print "WARNING: overrides will be added for OLDstable!"
    for pkg in new.keys():
        if new[pkg].has_key("othercomponents"):
            print "WARNING: %s already present in %s distribution." % (pkg, new[pkg]["othercomponents"])

    return new

################################################################################

def indiv_sg_compare (a, b):
    """Sort by source name, source, version, 'have source', and
       finally by filename."""
    # Sort by source version
    q = apt_pkg.VersionCompare(a["version"], b["version"])
    if q:
        return -q

    # Sort by 'have source'
    a_has_source = a["architecture"].get("source")
    b_has_source = b["architecture"].get("source")
    if a_has_source and not b_has_source:
        return -1
    elif b_has_source and not a_has_source:
        return 1

    return cmp(a["filename"], b["filename"])

############################################################

def sg_compare (a, b):
    a = a[1]
    b = b[1]
    """Sort by have note, time of oldest upload."""
    # Sort by have note
    a_note_state = a["note_state"]
    b_note_state = b["note_state"]
    if a_note_state < b_note_state:
        return -1
    elif a_note_state > b_note_state:
        return 1

    # Sort by time of oldest upload
    return cmp(a["oldest"], b["oldest"])

def sort_changes(changes_files):
    """Sort into source groups, then sort each source group by version,
    have source, filename.  Finally, sort the source groups by have
    note, time of oldest upload of each source upload."""
    if len(changes_files) == 1:
        return changes_files

    sorted_list = []
    cache = {}
    # Read in all the .changes files
    for filename in changes_files:
        try:
            Upload.pkg.changes_file = filename
            Upload.init_vars()
            Upload.update_vars()
            cache[filename] = copy.copy(Upload.pkg.changes)
            cache[filename]["filename"] = filename
        except:
            sorted_list.append(filename)
            break
    # Divide the .changes into per-source groups
    per_source = {}
    for filename in cache.keys():
        source = cache[filename]["source"]
        if not per_source.has_key(source):
            per_source[source] = {}
            per_source[source]["list"] = []
        per_source[source]["list"].append(cache[filename])
    # Determine oldest time and have note status for each source group
    for source in per_source.keys():
        source_list = per_source[source]["list"]
        first = source_list[0]
        oldest = os.stat(first["filename"])[stat.ST_MTIME]
        have_note = 0
        for d in per_source[source]["list"]:
            mtime = os.stat(d["filename"])[stat.ST_MTIME]
            if mtime < oldest:
                oldest = mtime
            have_note += (d.has_key("process-new note"))
        per_source[source]["oldest"] = oldest
        if not have_note:
            per_source[source]["note_state"] = 0; # none
        elif have_note < len(source_list):
            per_source[source]["note_state"] = 1; # some
        else:
            per_source[source]["note_state"] = 2; # all
        per_source[source]["list"].sort(indiv_sg_compare)
    per_source_items = per_source.items()
    per_source_items.sort(sg_compare)
    for i in per_source_items:
        for j in i[1]["list"]:
            sorted_list.append(j["filename"])
    return sorted_list

################################################################################

class Section_Completer:
    def __init__ (self):
        self.sections = []
        q = projectB.query("SELECT section FROM section")
        for i in q.getresult():
            self.sections.append(i[0])

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
    def __init__ (self):
        self.priorities = []
        q = projectB.query("SELECT priority FROM priority")
        for i in q.getresult():
            self.priorities.append(i[0])

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

def check_valid (new):
    for pkg in new.keys():
        section = new[pkg]["section"]
        priority = new[pkg]["priority"]
        type = new[pkg]["type"]
        new[pkg]["section id"] = daklib.database.get_section_id(section)
        new[pkg]["priority id"] = daklib.database.get_priority_id(new[pkg]["priority"])
        # Sanity checks
        di = section.find("debian-installer") != -1
        if (di and type != "udeb") or (not di and type == "udeb"):
            new[pkg]["section id"] = -1
        if (priority == "source" and type != "dsc") or \
           (priority != "source" and type == "dsc"):
            new[pkg]["priority id"] = -1

################################################################################

def print_new (new, indexed, file=sys.stdout):
    check_valid(new)
    broken = 0
    index = 0
    for pkg in new.keys():
        index += 1
        section = new[pkg]["section"]
        priority = new[pkg]["priority"]
        if new[pkg]["section id"] == -1:
            section += "[!]"
            broken = 1
        if new[pkg]["priority id"] == -1:
            priority += "[!]"
            broken = 1
        if indexed:
            line = "(%s): %-20s %-20s %-20s" % (index, pkg, priority, section)
        else:
            line = "%-20s %-20s %-20s" % (pkg, priority, section)
        line = line.strip()+'\n'
        file.write(line)
    note = Upload.pkg.changes.get("process-new note")
    if note:
        print "*"*75
        print note
        print "*"*75
    return broken, note

################################################################################

def get_type (f):
    # Determine the type
    if f.has_key("dbtype"):
        type = f["dbtype"]
    elif f["type"] == "orig.tar.gz" or f["type"] == "tar.gz" or f["type"] == "diff.gz" or f["type"] == "dsc":
        type = "dsc"
    else:
        daklib.utils.fubar("invalid type (%s) for new.  Dazed, confused and sure as heck not continuing." % (type))

    # Validate the override type
    type_id = daklib.database.get_override_type_id(type)
    if type_id == -1:
        daklib.utils.fubar("invalid type (%s) for new.  Say wha?" % (type))

    return type

################################################################################

def index_range (index):
    if index == 1:
        return "1"
    else:
        return "1-%s" % (index)

################################################################################
################################################################################

def edit_new (new):
    # Write the current data to a temporary file
    temp_filename = daklib.utils.temp_filename()
    temp_file = daklib.utils.open_file(temp_filename, 'w')
    print_new (new, 0, temp_file)
    temp_file.close()
    # Spawn an editor on that file
    editor = os.environ.get("EDITOR","vi")
    result = os.system("%s %s" % (editor, temp_filename))
    if result != 0:
        daklib.utils.fubar ("%s invocation failed for %s." % (editor, temp_filename), result)
    # Read the edited data back in
    temp_file = daklib.utils.open_file(temp_filename)
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
            daklib.utils.warn("Ignoring unknown package '%s'" % (pkg))
        else:
            # Strip off any invalid markers, print_new will readd them.
            if section.endswith("[!]"):
                section = section[:-3]
            if priority.endswith("[!]"):
                priority = priority[:-3]
            for file in new[pkg]["files"]:
                Upload.pkg.files[file]["section"] = section
                Upload.pkg.files[file]["priority"] = priority
            new[pkg]["section"] = section
            new[pkg]["priority"] = priority

################################################################################

def edit_index (new, index):
    priority = new[index]["priority"]
    section = new[index]["section"]
    type = new[index]["type"]
    done = 0
    while not done:
        print "\t".join([index, priority, section])

        answer = "XXX"
        if type != "dsc":
            prompt = "[B]oth, Priority, Section, Done ? "
        else:
            prompt = "[S]ection, Done ? "
        edit_priority = edit_section = 0

        while prompt.find(answer) == -1:
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.match(prompt)
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
                new_priority = daklib.utils.our_raw_input("New priority: ").strip()
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
                new_section = daklib.utils.our_raw_input("New section: ").strip()
                if new_section not in Sections.sections:
                    print "E: '%s' is not a valid section, try again." % (new_section)
                else:
                    got_section = 1
                    section = new_section

        # Reset the readline completer
        readline.set_completer(None)

    for file in new[index]["files"]:
        Upload.pkg.files[file]["section"] = section
        Upload.pkg.files[file]["priority"] = priority
    new[index]["priority"] = priority
    new[index]["section"] = section
    return new

################################################################################

def edit_overrides (new):
    print
    done = 0
    while not done:
        print_new (new, 1)
        new_index = {}
        index = 0
        for i in new.keys():
            index += 1
            new_index[index] = i

        prompt = "(%s) edit override <n>, Editor, Done ? " % (index_range(index))

        got_answer = 0
        while not got_answer:
            answer = daklib.utils.our_raw_input(prompt)
            if not answer.isdigit():
                answer = answer[:1].upper()
            if answer == "E" or answer == "D":
                got_answer = 1
            elif daklib.queue.re_isanum.match (answer):
                answer = int(answer)
                if (answer < 1) or (answer > index):
                    print "%s is not a valid index (%s).  Please retry." % (answer, index_range(index))
                else:
                    got_answer = 1

        if answer == 'E':
            edit_new(new)
        elif answer == 'D':
            done = 1
        else:
            edit_index (new, new_index[answer])

    return new

################################################################################

def edit_note(note):
    # Write the current data to a temporary file
    temp_filename = daklib.utils.temp_filename()
    temp_file = daklib.utils.open_file(temp_filename, 'w')
    temp_file.write(note)
    temp_file.close()
    editor = os.environ.get("EDITOR","vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        temp_file = daklib.utils.open_file(temp_filename)
        note = temp_file.read().rstrip()
        temp_file.close()
        print "Note:"
        print daklib.utils.prefix_multi_line_string(note,"  ")
        prompt = "[D]one, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
    os.unlink(temp_filename)
    if answer == 'A':
        return
    elif answer == 'Q':
        sys.exit(0)
    Upload.pkg.changes["process-new note"] = note
    Upload.dump_vars(Cnf["Dir::Queue::New"])

################################################################################

def check_pkg ():
    try:
        less_fd = os.popen("less -R -", 'w', 0)
        stdout_fd = sys.stdout
        try:
            sys.stdout = less_fd
            examine_package.display_changes(Upload.pkg.changes_file)
            files = Upload.pkg.files
            for file in files.keys():
                if files[file].has_key("new"):
                    type = files[file]["type"]
                    if type == "deb":
                        examine_package.check_deb(file)
                    elif type == "dsc":
                        examine_package.check_dsc(file)
        finally:
            sys.stdout = stdout_fd
    except IOError, e:
        if errno.errorcode[e.errno] == 'EPIPE':
            daklib.utils.warn("[examine_package] Caught EPIPE; skipping.")
            pass
        else:
            raise
    except KeyboardInterrupt:
        daklib.utils.warn("[examine_package] Caught C-c; skipping.")
        pass

################################################################################

## FIXME: horribly Debian specific

def do_bxa_notification():
    files = Upload.pkg.files
    summary = ""
    for file in files.keys():
        if files[file]["type"] == "deb":
            control = apt_pkg.ParseSection(apt_inst.debExtractControl(daklib.utils.open_file(file)))
            summary += "\n"
            summary += "Package: %s\n" % (control.Find("Package"))
            summary += "Description: %s\n" % (control.Find("Description"))
    Upload.Subst["__BINARY_DESCRIPTIONS__"] = summary
    bxa_mail = daklib.utils.TemplateSubst(Upload.Subst,Cnf["Dir::Templates"]+"/process-new.bxa_notification")
    daklib.utils.send_mail(bxa_mail)

################################################################################

def add_overrides (new):
    changes = Upload.pkg.changes
    files = Upload.pkg.files

    projectB.query("BEGIN WORK")
    for suite in changes["suite"].keys():
        suite_id = daklib.database.get_suite_id(suite)
        for pkg in new.keys():
            component_id = daklib.database.get_component_id(new[pkg]["component"])
            type_id = daklib.database.get_override_type_id(new[pkg]["type"])
            priority_id = new[pkg]["priority id"]
            section_id = new[pkg]["section id"]
            projectB.query("INSERT INTO override (suite, component, type, package, priority, section, maintainer) VALUES (%s, %s, %s, '%s', %s, %s, '')" % (suite_id, component_id, type_id, pkg, priority_id, section_id))
            for file in new[pkg]["files"]:
                if files[file].has_key("new"):
                    del files[file]["new"]
            del new[pkg]

    projectB.query("COMMIT WORK")

    if Cnf.FindB("Dinstall::BXANotify"):
        do_bxa_notification()

################################################################################

def prod_maintainer ():
    # Here we prepare an editor and get them ready to prod...
    temp_filename = daklib.utils.temp_filename()
    editor = os.environ.get("EDITOR","vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        file = daklib.utils.open_file(temp_filename)
        prod_message = "".join(file.readlines())
        file.close()
        print "Prod message:"
        print daklib.utils.prefix_multi_line_string(prod_message,"  ",include_blank_lines=1)
        prompt = "[P]rod, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
        os.unlink(temp_filename)
        if answer == 'A':
            return
        elif answer == 'Q':
            sys.exit(0)
    # Otherwise, do the proding...
    user_email_address = daklib.utils.whoami() + " <%s>" % (
        Cnf["Dinstall::MyAdminAddress"])

    Subst = Upload.Subst

    Subst["__FROM_ADDRESS__"] = user_email_address
    Subst["__PROD_MESSAGE__"] = prod_message
    Subst["__CC__"] = "Cc: " + Cnf["Dinstall::MyEmailAddress"]

    prod_mail_message = daklib.utils.TemplateSubst(
        Subst,Cnf["Dir::Templates"]+"/process-new.prod")

    # Send the prod mail if appropriate
    if not Cnf["Dinstall::Options::No-Mail"]:
        daklib.utils.send_mail(prod_mail_message)

    print "Sent proding message"

################################################################################

def do_new():
    print "NEW\n"
    files = Upload.pkg.files
    changes = Upload.pkg.changes

    # Make a copy of distribution we can happily trample on
    changes["suite"] = copy.copy(changes["distribution"])

    # Fix up the list of target suites
    for suite in changes["suite"].keys():
        override = Cnf.Find("Suite::%s::OverrideSuite" % (suite))
        if override:
	    (olderr, newerr) = (daklib.database.get_suite_id(suite) == -1,
	      daklib.database.get_suite_id(override) == -1)
	    if olderr or newerr:
	        (oinv, newinv) = ("", "")
		if olderr: oinv = "invalid "
		if newerr: ninv = "invalid "
	        print "warning: overriding %ssuite %s to %ssuite %s" % (
			oinv, suite, ninv, override)
            del changes["suite"][suite]
            changes["suite"][override] = 1
    # Validate suites
    for suite in changes["suite"].keys():
        suite_id = daklib.database.get_suite_id(suite)
        if suite_id == -1:
            daklib.utils.fubar("%s has invalid suite '%s' (possibly overriden).  say wha?" % (changes, suite))

    # The main NEW processing loop
    done = 0
    while not done:
        # Find out what's new
        new = determine_new(changes, files)

        if not new:
            break

        answer = "XXX"
        if Options["No-Action"] or Options["Automatic"]:
            answer = 'S'

        (broken, note) = print_new(new, 0)
        prompt = ""

        if not broken and not note:
            prompt = "Add overrides, "
        if broken:
            print "W: [!] marked entries must be fixed before package can be processed."
        if note:
            print "W: note must be removed before package can be processed."
            prompt += "Remove note, "

        prompt += "Edit overrides, Check, Manual reject, Note edit, Prod, [S]kip, Quit ?"

        while prompt.find(answer) == -1:
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'A':
            done = add_overrides (new)
        elif answer == 'C':
            check_pkg()
        elif answer == 'E':
            new = edit_overrides (new)
        elif answer == 'M':
            aborted = Upload.do_reject(1, Options["Manual-Reject"])
            if not aborted:
                os.unlink(Upload.pkg.changes_file[:-8]+".dak")
                done = 1
        elif answer == 'N':
            edit_note(changes.get("process-new note", ""))
        elif answer == 'P':
            prod_maintainer()
        elif answer == 'R':
            confirm = daklib.utils.our_raw_input("Really clear note (y/N)? ").lower()
            if confirm == "y":
                del changes["process-new note"]
        elif answer == 'S':
            done = 1
        elif answer == 'Q':
            sys.exit(0)

################################################################################
################################################################################
################################################################################

def usage (exit_code=0):
    print """Usage: dak process-new [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -h, --help                show this help and exit.
  -m, --manual-reject=MSG   manual reject with `msg'
  -n, --no-action           don't do anything
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

################################################################################

def init():
    global Cnf, Options, Logger, Upload, projectB, Sections, Priorities

    Cnf = daklib.utils.get_conf()

    Arguments = [('a',"automatic","Process-New::Options::Automatic"),
                 ('h',"help","Process-New::Options::Help"),
                 ('m',"manual-reject","Process-New::Options::Manual-Reject", "HasArg"),
                 ('n',"no-action","Process-New::Options::No-Action")]

    for i in ["automatic", "help", "manual-reject", "no-action", "version"]:
        if not Cnf.has_key("Process-New::Options::%s" % (i)):
            Cnf["Process-New::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Process-New::Options")

    if Options["Help"]:
        usage()

    Upload = daklib.queue.Upload(Cnf)

    if not Options["No-Action"]:
        Logger = Upload.Logger = daklib.logging.Logger(Cnf, "process-new")

    projectB = Upload.projectB

    Sections = Section_Completer()
    Priorities = Priority_Completer()
    readline.parse_and_bind("tab: complete")

    return changes_files

################################################################################

def do_byhand():
    done = 0
    while not done:
        files = Upload.pkg.files
        will_install = 1
        byhand = []

        for file in files.keys():
            if files[file]["type"] == "byhand":
                if os.path.exists(file):
                    print "W: %s still present; please process byhand components and try again." % (file)
                    will_install = 0
                else:
                    byhand.append(file)

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
            answer = daklib.utils.our_raw_input(prompt)
            m = daklib.queue.re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()

        if answer == 'A':
            done = 1
            for file in byhand:
                del files[file]
        elif answer == 'M':
            Upload.do_reject(1, Options["Manual-Reject"])
            os.unlink(Upload.pkg.changes_file[:-8]+".dak")
            done = 1
        elif answer == 'S':
            done = 1
        elif answer == 'Q':
            sys.exit(0)

################################################################################

def do_accept():
    print "ACCEPT"
    if not Options["No-Action"]:
        retry = 0
	while retry < 10:
	    try:
		lock_fd = os.open(Cnf["Process-New::AcceptedLockFile"], os.O_RDONLY | os.O_CREAT | os.O_EXCL)
                retry = 10
	    except OSError, e:
		if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EEXIST':
		    retry += 1
		    if (retry >= 10):
			daklib.utils.fubar("Couldn't obtain lock; assuming 'dak process-unchecked' is already running.")
		    else:
			print("Unable to get accepted lock (try %d of 10)" % retry)
		    time.sleep(60)
		else:
		    raise
        (summary, short_summary) = Upload.build_summaries()
        Upload.accept(summary, short_summary)
        os.unlink(Upload.pkg.changes_file[:-8]+".dak")
	os.unlink(Cnf["Process-New::AcceptedLockFile"])

def check_status(files):
    new = byhand = 0
    for file in files.keys():
        if files[file]["type"] == "byhand":
            byhand = 1
        elif files[file].has_key("new"):
            new = 1
    return (new, byhand)

def do_pkg(changes_file):
    Upload.pkg.changes_file = changes_file
    Upload.init_vars()
    Upload.update_vars()
    Upload.update_subst()
    files = Upload.pkg.files

    if not recheck():
        return

    (new, byhand) = check_status(files)
    if new or byhand:
        if new:
            do_new()
        if byhand:
            do_byhand()
        (new, byhand) = check_status(files)

    if not new and not byhand:
        do_accept()

################################################################################

def end():
    accept_count = Upload.accept_count
    accept_bytes = Upload.accept_bytes

    if accept_count:
        sets = "set"
        if accept_count > 1:
            sets = "sets"
        sys.stderr.write("Accepted %d package %s, %s.\n" % (accept_count, sets, daklib.utils.size_type(int(accept_bytes))))
        Logger.log(["total",accept_count,accept_bytes])

    if not Options["No-Action"]:
        Logger.close()

################################################################################

def main():
    changes_files = init()
    if len(changes_files) > 50:
        sys.stderr.write("Sorting changes...\n")
    changes_files = sort_changes(changes_files)

    # Kill me now? **FIXME**
    Cnf["Dinstall::Options::No-Mail"] = ""
    bcc = "X-DAK: dak process-new\nX-Katie: lisa $Revision: 1.31 $"
    if Cnf.has_key("Dinstall::Bcc"):
        Upload.Subst["__BCC__"] = bcc + "\nBcc: %s" % (Cnf["Dinstall::Bcc"])
    else:
        Upload.Subst["__BCC__"] = bcc

    for changes_file in changes_files:
        changes_file = daklib.utils.validate_changes_file_arg(changes_file, 0)
        if not changes_file:
            continue
        print "\n" + changes_file
        do_pkg (changes_file)

    end()

################################################################################

if __name__ == '__main__':
    main()
