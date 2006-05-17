#!/usr/bin/env python

# Create all the Release files

# Copyright (C) 2001, 2002, 2006  Anthony Towns <ajt@debian.org>

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

#   ``Bored now''

################################################################################

import sys, os, popen2, tempfile, stat, time
import apt_pkg
import dak.lib.utils as utils

################################################################################

Cnf = None
projectB = None
out = None
AptCnf = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak generate-releases [OPTION]... [SUITE]...
Generate Release files (for SUITE).

  -h, --help                 show this help and exit

If no SUITE is given Release files are generated for all suites."""

    sys.exit(exit_code)

################################################################################

def add_tiffani (files, path, indexstem):
    index = "%s.diff/Index" % (indexstem)
    filepath = "%s/%s" % (path, index)
    if os.path.exists(filepath):
        #print "ALERT: there was a tiffani file %s" % (filepath)
        files.append(index)

def compressnames (tree,type,file):
    compress = AptCnf.get("%s::%s::Compress" % (tree,type), AptCnf.get("Default::%s::Compress" % (type), ". gzip"))
    result = []
    cl = compress.split()
    uncompress = ("." not in cl)
    for mode in compress.split():
	if mode == ".":
	    result.append(file)
	elif mode == "gzip":
	    if uncompress:
		result.append("<zcat/.gz>" + file)
		uncompress = 0
	    result.append(file + ".gz")
	elif mode == "bzip2":
	    if uncompress:
		result.append("<bzcat/.bz2>" + file)
		uncompress = 0
	    result.append(file + ".bz2")
    return result

def create_temp_file (cmd):
    f = tempfile.TemporaryFile()
    r = popen2.popen2(cmd)
    r[1].close()
    r = r[0]
    size = 0
    while 1:
	x = r.readline()
	if not x:
	    r.close()
	    del x,r
	    break
	f.write(x)
	size += len(x)
    f.flush()
    f.seek(0)
    return (size, f)

def print_md5sha_files (tree, files, hashop):
    path = Cnf["Dir::Root"] + tree + "/"
    for name in files:
        try:
	    if name[0] == "<":
		j = name.index("/")
		k = name.index(">")
		(cat, ext, name) = (name[1:j], name[j+1:k], name[k+1:])
		(size, file_handle) = create_temp_file("%s %s%s%s" %
		    (cat, path, name, ext))
	    else:
        	size = os.stat(path + name)[stat.ST_SIZE]
       	        file_handle = utils.open_file(path + name)
        except utils.cant_open_exc:
            print "ALERT: Couldn't open " + path + name
        else:
	    hash = hashop(file_handle)
	    file_handle.close()
	    out.write(" %s         %8d %s\n" % (hash, size, name))

def print_md5_files (tree, files):
    print_md5sha_files (tree, files, apt_pkg.md5sum)

def print_sha1_files (tree, files):
    print_md5sha_files (tree, files, apt_pkg.sha1sum)

################################################################################

def main ():
    global Cnf, AptCnf, projectB, out
    out = sys.stdout

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Generate-Releases::Options::Help")]
    for i in [ "help" ]:
	if not Cnf.has_key("Generate-Releases::Options::%s" % (i)):
	    Cnf["Generate-Releases::Options::%s" % (i)] = ""

    suites = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Generate-Releases::Options")

    if Options["Help"]:
	usage()

    AptCnf = apt_pkg.newConfiguration()
    apt_pkg.ReadConfigFileISC(AptCnf,utils.which_apt_conf_file())

    if not suites:
        suites = Cnf.SubTree("Suite").List()

    for suite in suites:
        print "Processing: " + suite
	SuiteBlock = Cnf.SubTree("Suite::" + suite)

	if SuiteBlock.has_key("Untouchable"):
            print "Skipping: " + suite + " (untouchable)"
            continue

	suite = suite.lower()

	origin = SuiteBlock["Origin"]
	label = SuiteBlock.get("Label", origin)
	version = SuiteBlock.get("Version", "")
	codename = SuiteBlock.get("CodeName", "")

	if SuiteBlock.has_key("NotAutomatic"):
	    notautomatic = "yes"
	else:
	    notautomatic = ""

	if SuiteBlock.has_key("Components"):
	    components = SuiteBlock.ValueList("Components")
	else:
	    components = []

        suite_suffix = Cnf.Find("Dinstall::SuiteSuffix")
        if components and suite_suffix:
            longsuite = suite + "/" + suite_suffix
        else:
            longsuite = suite

	tree = SuiteBlock.get("Tree", "dists/%s" % (longsuite))

	if AptCnf.has_key("tree::%s" % (tree)):
	    pass
	elif AptCnf.has_key("bindirectory::%s" % (tree)):
	    pass
	else:
            aptcnf_filename = os.path.basename(utils.which_apt_conf_file())
	    print "ALERT: suite %s not in %s, nor untouchable!" % (suite, aptcnf_filename)
	    continue

	print Cnf["Dir::Root"] + tree + "/Release"
	out = open(Cnf["Dir::Root"] + tree + "/Release", "w")

	out.write("Origin: %s\n" % (origin))
	out.write("Label: %s\n" % (label))
	out.write("Suite: %s\n" % (suite))
	if version != "":
	    out.write("Version: %s\n" % (version))
	if codename != "":
	    out.write("Codename: %s\n" % (codename))
	out.write("Date: %s\n" % (time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(time.time()))))
	if notautomatic != "":
	    out.write("NotAutomatic: %s\n" % (notautomatic))
	out.write("Architectures: %s\n" % (" ".join(filter(utils.real_arch, SuiteBlock.ValueList("Architectures")))))
	if components:
            out.write("Components: %s\n" % (" ".join(components)))

	out.write("Description: %s\n" % (SuiteBlock["Description"]))

	files = []

	if AptCnf.has_key("tree::%s" % (tree)):
	    for sec in AptCnf["tree::%s::Sections" % (tree)].split():
		for arch in AptCnf["tree::%s::Architectures" % (tree)].split():
		    if arch == "source":
		        filepath = "%s/%s/Sources" % (sec, arch)
			for file in compressnames("tree::%s" % (tree), "Sources", filepath):
			    files.append(file)
			add_tiffani(files, Cnf["Dir::Root"] + tree, filepath)
		    else:
			disks = "%s/disks-%s" % (sec, arch)
			diskspath = Cnf["Dir::Root"]+tree+"/"+disks
			if os.path.exists(diskspath):
			    for dir in os.listdir(diskspath):
				if os.path.exists("%s/%s/md5sum.txt" % (diskspath, dir)):
				    files.append("%s/%s/md5sum.txt" % (disks, dir))

			filepath = "%s/binary-%s/Packages" % (sec, arch)
			for file in compressnames("tree::%s" % (tree), "Packages", filepath):
			    files.append(file)
			add_tiffani(files, Cnf["Dir::Root"] + tree, filepath)

		    if arch == "source":
			rel = "%s/%s/Release" % (sec, arch)
		    else:
			rel = "%s/binary-%s/Release" % (sec, arch)
		    relpath = Cnf["Dir::Root"]+tree+"/"+rel

                    try:
                        release = open(relpath, "w")
                        #release = open(longsuite.replace("/","_") + "_" + arch + "_" + sec + "_Release", "w")
                    except IOError:
                        utils.fubar("Couldn't write to " + relpath)

                    release.write("Archive: %s\n" % (suite))
                    if version != "":
                        release.write("Version: %s\n" % (version))
                    if suite_suffix:
                        release.write("Component: %s/%s\n" % (suite_suffix,sec))
                    else:
                        release.write("Component: %s\n" % (sec))
                    release.write("Origin: %s\n" % (origin))
                    release.write("Label: %s\n" % (label))
                    if notautomatic != "":
                        release.write("NotAutomatic: %s\n" % (notautomatic))
                    release.write("Architecture: %s\n" % (arch))
                    release.close()
                    files.append(rel)

	    if AptCnf.has_key("tree::%s/main" % (tree)):
	        sec = AptCnf["tree::%s/main::Sections" % (tree)].split()[0]
		if sec != "debian-installer":
	    	    print "ALERT: weird non debian-installer section in %s" % (tree)

		for arch in AptCnf["tree::%s/main::Architectures" % (tree)].split():
		    if arch != "source":  # always true
			for file in compressnames("tree::%s/main" % (tree), "Packages", "main/%s/binary-%s/Packages" % (sec, arch)):
			    files.append(file)
	    elif AptCnf.has_key("tree::%s::FakeDI" % (tree)):
		usetree = AptCnf["tree::%s::FakeDI" % (tree)]
		sec = AptCnf["tree::%s/main::Sections" % (usetree)].split()[0]
		if sec != "debian-installer":
		    print "ALERT: weird non debian-installer section in %s" % (usetree)
 
		for arch in AptCnf["tree::%s/main::Architectures" % (usetree)].split():
		    if arch != "source":  # always true
			for file in compressnames("tree::%s/main" % (usetree), "Packages", "main/%s/binary-%s/Packages" % (sec, arch)):
			    files.append(file)

	elif AptCnf.has_key("bindirectory::%s" % (tree)):
	    for file in compressnames("bindirectory::%s" % (tree), "Packages", AptCnf["bindirectory::%s::Packages" % (tree)]):
		files.append(file.replace(tree+"/","",1))
	    for file in compressnames("bindirectory::%s" % (tree), "Sources", AptCnf["bindirectory::%s::Sources" % (tree)]):
		files.append(file.replace(tree+"/","",1))
	else:
	    print "ALERT: no tree/bindirectory for %s" % (tree)

	out.write("MD5Sum:\n")
	print_md5_files(tree, files)
	out.write("SHA1:\n")
	print_sha1_files(tree, files)

	out.close()
	if Cnf.has_key("Dinstall::SigningKeyring"):
	    keyring = "--secret-keyring \"%s\"" % Cnf["Dinstall::SigningKeyring"]
	    if Cnf.has_key("Dinstall::SigningPubKeyring"):
		keyring += " --keyring \"%s\"" % Cnf["Dinstall::SigningPubKeyring"]

	    arguments = "--no-options --batch --no-tty --armour"
	    if Cnf.has_key("Dinstall::SigningKeyIds"):
		signkeyids = Cnf["Dinstall::SigningKeyIds"].split()
	    else:
		signkeyids = [""]

	    dest = Cnf["Dir::Root"] + tree + "/Release.gpg"
	    if os.path.exists(dest):
		os.unlink(dest)

	    for keyid in signkeyids:
		if keyid != "": defkeyid = "--default-key %s" % keyid
		else: defkeyid = ""
		os.system("gpg %s %s %s --detach-sign <%s >>%s" %
			(keyring, defkeyid, arguments,
			Cnf["Dir::Root"] + tree + "/Release", dest))

#######################################################################################

if __name__ == '__main__':
    main()

