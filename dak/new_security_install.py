#!/usr/bin/env python

import katie, logging, utils, db_access
import apt_pkg, os, sys, pwd, time, re, commands

re_taint_free = re.compile(r"^['/;\-\+\.\s\w]+$");

Cnf = None
Options = None
Katie = None
Logger = None

advisory = None
changes = []
srcverarches = {}

def init():
    global Cnf, Katie, Options, Logger

    Cnf = utils.get_conf()
    Cnf["Dinstall::Options::No-Mail"] = "y"
    Arguments = [('h', "help", "Amber::Options::Help"),
                 ('a', "automatic", "Amber::Options::Automatic"),
                 ('n', "no-action", "Amber::Options::No-Action"),
		 ('s', "sudo", "Amber::Options::Sudo"),
		 (' ', "no-upload", "Amber::Options::No-Upload"),
		 (' ', "drop-advisory", "Amber::Options::Drop-Advisory"),
		 ('A', "approve", "Amber::Options::Approve"),
		 ('R', "reject", "Amber::Options::Reject"),
		 ('D', "disembargo", "Amber::Options::Disembargo") ]

    for i in Arguments:
         Cnf[i[2]] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Amber::Options")

    whoami = os.getuid()
    whoamifull = pwd.getpwuid(whoami)
    username = whoamifull[0]
    if username != "katie":
        print "Non-katie user: %s" % username
        Options["Sudo"] = "y"

    if Options["Help"]:
        print "help yourself"
	sys.exit(0)

    if len(arguments) == 0:
       utils.fubar("Process what?")

    Katie = katie.Katie(Cnf)
    if not Options["Sudo"] and not Options["No-Action"]:
        Logger = Katie.Logger = logging.Logger(Cnf, "newamber")

    return arguments

def quit():
    if Logger:
        Logger.close()
    sys.exit(0)

def load_args(arguments):
    global advisory, changes

    adv_ids = {}
    if not arguments[0].endswith(".changes"):
       adv_ids [arguments[0]] = 1
       arguments = arguments[1:]

    null_adv_changes = []

    changesfiles = {}
    for a in arguments:
        if "/" in a:
            utils.fubar("can only deal with files in the current directory")
        if not a.endswith(".changes"):
            utils.fubar("not a .changes file: %s" % (a))
        Katie.init_vars()
        Katie.pkg.changes_file = a
        Katie.update_vars()
        if "adv id" in Katie.pkg.changes:
            changesfiles[a] = 1
            adv_ids[Katie.pkg.changes["adv id"]] = 1
        else:
            null_adv_changes.append(a)

    adv_ids = adv_ids.keys()
    if len(adv_ids) > 1:
        utils.fubar("multiple advisories selected: %s" % (", ".join(adv_ids)))
    if adv_ids == []:
        advisory = None
    else:
        advisory = adv_ids[0]

    changes = changesfiles.keys()
    return null_adv_changes

def load_adv_changes():
    global srcverarches, changes

    for c in os.listdir("."):
        if not c.endswith(".changes"): continue
        Katie.init_vars()
        Katie.pkg.changes_file = c
        Katie.update_vars()
        if "adv id" not in Katie.pkg.changes:
	    continue
	if Katie.pkg.changes["adv id"] != advisory:
	    continue

	if c not in changes: changes.append(c)
        srcver = "%s %s" % (Katie.pkg.changes["source"], 
	                    Katie.pkg.changes["version"])
        srcverarches.setdefault(srcver, {})
        for arch in Katie.pkg.changes["architecture"].keys():
            srcverarches[srcver][arch] = 1

def advisory_info():
    if advisory != None:
        print "Advisory: %s" % (advisory)
    print "Changes:"
    for c in changes:
        print " %s" % (c)

    print "Packages:"
    svs = srcverarches.keys()
    svs.sort()
    for sv in svs:
        as = srcverarches[sv].keys()
        as.sort()
        print " %s (%s)" % (sv, ", ".join(as))

def prompt(opts, default):
    p = ""
    v = {}
    for o in opts:
        v[o[0].upper()] = o
        if o[0] == default:
	    p += ", [%s]%s" % (o[0], o[1:])
	else:
	    p += ", " + o
    p = p[2:] + "? "
    a = None

    if Options["Automatic"]:
        a = default

    while a not in v:
        a = utils.our_raw_input(p) + default
	a = a[:1].upper()
	
    return v[a]

def add_changes(extras):
    for c in extras:
	changes.append(c)
        Katie.init_vars()
        Katie.pkg.changes_file = c
        Katie.update_vars()
        srcver = "%s %s" % (Katie.pkg.changes["source"], Katie.pkg.changes["version"])
        srcverarches.setdefault(srcver, {})
        for arch in Katie.pkg.changes["architecture"].keys():
            srcverarches[srcver][arch] = 1
	Katie.pkg.changes["adv id"] = advisory
	Katie.dump_vars(os.getcwd())

def yes_no(prompt):
    if Options["Automatic"]: return True
    while 1:
        answer = utils.our_raw_input(prompt + " ").lower()
	if answer in "yn":
	    return answer == "y"
	print "Invalid answer; please try again."

def do_upload():
    if Options["No-Upload"]:
        print "Not uploading as requested"
	return

    print "Would upload to ftp-master" # XXX

def generate_advisory(template):
    global changes, advisory

    adv_packages = []
    updated_pkgs = {};  # updated_pkgs[distro][arch][file] = {path,md5,size}

    for arg in changes:
        arg = utils.validate_changes_file_arg(arg)
	Katie.pkg.changes_file = arg
	Katie.init_vars()
	Katie.update_vars()

        src = Katie.pkg.changes["source"]
	src_ver = "%s (%s)" % (src, Katie.pkg.changes["version"])
	if src_ver not in adv_packages:
	    adv_packages.append(src_ver)

	suites = Katie.pkg.changes["distribution"].keys()
	for suite in suites:
	    if not updated_pkgs.has_key(suite):
                updated_pkgs[suite] = {}

	files = Katie.pkg.files
	for file in files.keys():
	    arch = files[file]["architecture"]
	    md5 = files[file]["md5sum"]
	    size = files[file]["size"]
	    poolname = Cnf["Dir::PoolRoot"] + \
	    	utils.poolify(src, files[file]["component"])
	    if arch == "source" and file.endswith(".dsc"):
	        dscpoolname = poolname
	    for suite in suites:
	        if not updated_pkgs[suite].has_key(arch):
		    updated_pkgs[suite][arch] = {}
		updated_pkgs[suite][arch][file] = {
                    "md5": md5, "size": size, "poolname": poolname }

	dsc_files = Katie.pkg.dsc_files
	for file in dsc_files.keys():
	    arch = "source"
	    if not dsc_files[file].has_key("files id"):
                continue

	    # otherwise, it's already in the pool and needs to be
	    # listed specially
	    md5 = dsc_files[file]["md5sum"]
	    size = dsc_files[file]["size"]
	    for suite in suites:
	        if not updated_pkgs[suite].has_key(arch):
		    updated_pkgs[suite][arch] = {}
		updated_pkgs[suite][arch][file] = {
                    "md5": md5, "size": size, "poolname": dscpoolname }

    if os.environ.has_key("SUDO_UID"):
        whoami = long(os.environ["SUDO_UID"])
    else:
        whoami = os.getuid()
    whoamifull = pwd.getpwuid(whoami)
    username = whoamifull[4].split(",")[0]

    Subst = {
    	"__ADVISORY__": advisory,
	"__WHOAMI__": username,
	"__DATE__": time.strftime("%B %d, %Y", time.gmtime(time.time())),
	"__PACKAGE__": ", ".join(adv_packages),
        "__KATIE_ADDRESS__": Cnf["Dinstall::MyEmailAddress"]
        }

    if Cnf.has_key("Dinstall::Bcc"):
        Subst["__BCC__"] = "Bcc: %s" % (Cnf["Dinstall::Bcc"])

    adv = ""
    archive = Cnf["Archive::%s::PrimaryMirror" % (utils.where_am_i())]
    for suite in updated_pkgs.keys():
        ver = Cnf["Suite::%s::Version" % suite]
	if ver != "": ver += " "
        suite_header = "%s %s(%s)" % (Cnf["Dinstall::MyDistribution"],
                                       ver, suite)
        adv += "%s\n%s\n\n" % (suite_header, "-"*len(suite_header))

	arches = Cnf.ValueList("Suite::%s::Architectures" % suite)
	if "source" in arches:
            arches.remove("source")
	if "all" in arches:
            arches.remove("all")
	arches.sort()

	adv += "%s updates are available for %s.\n\n" % (
		suite.capitalize(), utils.join_with_commas_and(arches))

	for a in ["source", "all"] + arches:
	    if not updated_pkgs[suite].has_key(a):
                continue

	    if a == "source":
	    	adv += "Source archives:\n\n"
	    elif a == "all":
	        adv += "Architecture independent packages:\n\n"
	    else:
	        adv += "%s architecture (%s)\n\n" % (a,
			Cnf["Architectures::%s" % a])

	    for file in updated_pkgs[suite][a].keys():
		adv += "  http://%s/%s%s\n" % (
				archive, updated_pkgs[suite][a][file]["poolname"], file)
		adv += "    Size/MD5 checksum: %8s %s\n" % (
			updated_pkgs[suite][a][file]["size"],
			updated_pkgs[suite][a][file]["md5"])
	    adv += "\n"
    adv = adv.rstrip()

    Subst["__ADVISORY_TEXT__"] = adv

    adv = utils.TemplateSubst(Subst, template)
    return adv


def spawn(command):
    if not re_taint_free.match(command):
        utils.fubar("Invalid character in \"%s\"." % (command))

    if Options["No-Action"]:
        print "[%s]" % (command)
    else:
        (result, output) = commands.getstatusoutput(command)
        if (result != 0):
            utils.fubar("Invocation of '%s' failed:\n%s\n" % (command, output), result)


##################### ! ! ! N O T E ! ! !  #####################
#
# These functions will be reinvoked by semi-priveleged users, be careful not
# to invoke external programs that will escalate privileges, etc.
#
##################### ! ! ! N O T E ! ! !  #####################

def sudo(arg, fn, exit):
    if Options["Sudo"]:
        if advisory == None:
	    utils.fubar("Must set advisory name")
        os.spawnl(os.P_WAIT, "/usr/bin/sudo","/usr/bin/sudo", "-u", "katie", "-H", 
	   "/org/security.debian.org/katie/newamber", "-"+arg, "--", advisory)
    else:
        fn()
    if exit:
        quit()

def do_Approve(): sudo("A", _do_Approve, True)
def _do_Approve():
    # 1. dump advisory in drafts
    draft = "/org/security.debian.org/advisories/drafts/%s" % (advisory)
    print "Advisory in %s" % (draft)
    if not Options["No-Action"]:
        adv_file = "./advisory.%s" % (advisory)
        if not os.path.exists(adv_file):
            adv_file = Cnf["Dir::Templates"]+"/amber.advisory"
        adv_fd = os.open(draft, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0664)
        os.write(adv_fd, generate_advisory(adv_file))
        os.close(adv_fd)
        adv_fd = None

    # 2. run kelly on changes
    print "Accepting packages..."
    spawn("%s/kelly -pa %s" % (Cnf["Dir::Katie"], " ".join(changes)))

    # 3. run jenna / apt-ftparchve / ziyi / tiffani
    if not Options["No-Action"]:
        os.chdir(Cnf["Dir::Katie"])

    print "Updating file lists for apt-ftparchive..."
    spawn("./jenna")
    print "Updating Packages and Sources files..."
    spawn("apt-ftparchive generate %s" % (utils.which_apt_conf_file()))
    print "Updating Release files..."
    spawn("./ziyi")
    print "Triggering security mirrors..."
    spawn("sudo -u archvsync /home/archvsync/signal_security")

    # 4. chdir to done - do upload
    if not Options["No-Action"]:
        os.chdir(Cnf["Dir::Queue::Done"])
    do_upload()

def do_Disembargo(): sudo("D", _do_Disembargo, True)
def _do_Disembargo():
    if os.getcwd() != Cnf["Dir::Queue::Embargoed"].rstrip("/"):
        utils.fubar("Can only disembargo from %s" % Cnf["Dir::Queue::Embargoed"])

    dest = Cnf["Dir::Queue::Unembargoed"]
    emb_q = db_access.get_or_set_queue_id("embargoed")
    une_q = db_access.get_or_set_queue_id("unembargoed")

    queuefiles = []
    for c in changes:
        print "Disembargoing %s" % (c)

        Katie.init_vars()
        Katie.pkg.changes_file = c
        Katie.update_vars()

        if "source" in Katie.pkg.changes["architecture"].keys():
	    print "Adding %s %s to disembargo table" % (Katie.pkg.changes["source"], Katie.pkg.changes["version"])
	    Katie.projectB.query("INSERT INTO disembargo (package, version) VALUES ('%s', '%s')" % (Katie.pkg.changes["source"], Katie.pkg.changes["version"]))

        files = {}
	for suite in Katie.pkg.changes["distribution"].keys():
	    if suite not in Cnf.ValueList("Dinstall::QueueBuildSuites"):
	        continue
	    dest_dir = Cnf["Dir::QueueBuild"]
	    if Cnf.FindB("Dinstall::SecurityQueueBuild"):
	        dest_dir = os.path.join(dest_dir, suite)
	    for file in Katie.pkg.files.keys():
	        files[os.path.join(dest_dir, file)] = 1

	files = files.keys()
	Katie.projectB.query("BEGIN WORK")
	for f in files:
	    Katie.projectB.query("UPDATE queue_build SET queue = %s WHERE filename = '%s' AND queue = %s" % (une_q, f, emb_q))
	Katie.projectB.query("COMMIT WORK")

	for file in Katie.pkg.files.keys():
	    utils.copy(file, os.path.join(dest, file))
	    os.unlink(file)

    for c in changes:
        utils.copy(c, os.path.join(dest, c))
	os.unlink(c)
	k = c[:8] + ".katie"
        utils.copy(k, os.path.join(dest, k))
	os.unlink(k)

def do_Reject(): sudo("R", _do_Reject, True)
def _do_Reject():
    global changes
    for c in changes:
        print "Rejecting %s..." % (c)
        Katie.init_vars()
        Katie.pkg.changes_file = c
        Katie.update_vars()
        files = {}
	for suite in Katie.pkg.changes["distribution"].keys():
	    if suite not in Cnf.ValueList("Dinstall::QueueBuildSuites"):
	        continue
	    dest_dir = Cnf["Dir::QueueBuild"]
	    if Cnf.FindB("Dinstall::SecurityQueueBuild"):
	        dest_dir = os.path.join(dest_dir, suite)
	    for file in Katie.pkg.files.keys():
	        files[os.path.join(dest_dir, file)] = 1

	files = files.keys()

	aborted = Katie.do_reject()
	if not aborted:
	    os.unlink(c[:-8]+".katie")
	    for f in files:
	        Katie.projectB.query(
		    "DELETE FROM queue_build WHERE filename = '%s'" % (f))
		os.unlink(f)

    print "Updating buildd information..."
    spawn("/org/security.debian.org/katie/cron.buildd-security")

    adv_file = "./advisory.%s" % (advisory)
    if os.path.exists(adv_file):
        os.unlink(adv_file)

def do_DropAdvisory():
    for c in changes:
        Katie.init_vars()
        Katie.pkg.changes_file = c
        Katie.update_vars()
	del Katie.pkg.changes["adv id"]
	Katie.dump_vars(os.getcwd())
    quit()

def do_Edit():
    adv_file = "./advisory.%s" % (advisory)
    if not os.path.exists(adv_file):
        utils.copy(Cnf["Dir::Templates"]+"/amber.advisory", adv_file)
    editor = os.environ.get("EDITOR","vi")
    result = os.system("%s %s" % (editor, adv_file))
    if result != 0:
        utils.fubar("%s invocation failed for %s." % (editor, adv_file))

def do_Show():
    adv_file = "./advisory.%s" % (advisory)
    if not os.path.exists(adv_file):
        adv_file = Cnf["Dir::Templates"]+"/amber.advisory"
    print "====\n%s\n====" % (generate_advisory(adv_file))

def do_Quit():
    quit()

def main():
    global changes

    args = init()
    extras = load_args(args)
    if advisory:
        load_adv_changes()
    if extras:
        if not advisory:
            changes = extras
	else:
            if srcverarches == {}:
                if not yes_no("Create new advisory %s?" % (advisory)):
		    print "Not doing anything, then"
		    quit()
            else:
                advisory_info()
	        doextras = []
                for c in extras:
	            if yes_no("Add %s to %s?" % (c, advisory)):
		         doextras.append(c)
                extras = doextras
            add_changes(extras)

    if not advisory:
        utils.fubar("Must specify an advisory id")

    if not changes:
        utils.fubar("No changes specified")

    if Options["Approve"]:
	advisory_info()
        do_Approve()
    elif Options["Reject"]:
	advisory_info()
        do_Reject()
    elif Options["Disembargo"]:
	advisory_info()
        do_Disembargo()
    elif Options["Drop-Advisory"]:
        advisory_info()
	do_DropAdvisory()
    else:
        while 1:
            default = "Q"
	    opts = ["Approve", "Edit advisory"]
	    if os.path.exists("./advisory.%s" % advisory):
	        default = "A"
	    else:
	        default = "E"
	    if os.getcwd() == Cnf["Dir::Queue::Embargoed"].rstrip("/"):
	        opts.append("Disembargo")
	    opts += ["Show advisory", "Reject", "Quit"]
	
	    advisory_info()
            what = prompt(opts, default)

	    if what == "Quit":
	        do_Quit()
	    elif what == "Approve":
	        do_Approve()
	    elif what == "Edit advisory":
	        do_Edit()
	    elif what == "Show advisory":
	        do_Show()
	    elif what == "Disembargo":
	        do_Disembargo()
	    elif what == "Reject":
	        do_Reject()
	    else:
	        utils.fubar("Impossible answer '%s', wtf?" % (what))

main()
