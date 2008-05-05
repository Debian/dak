#!/usr/bin/env python

# Populate the DB
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# 04:36|<aj> elmo: you're making me waste 5 seconds per architecture!!!!!! YOU BASTARD!!!!!

###############################################################################

# This code is a horrible mess for two reasons:

#   (o) For Debian's usage, it's doing something like 160k INSERTs,
#   even on auric, that makes the program unusable unless we get
#   involed in sorts of silly optimization games (local dicts to avoid
#   redundant SELECTS, using COPY FROM rather than INSERTS etc.)

#   (o) It's very site specific, because I don't expect to use this
#   script again in a hurry, and I don't want to spend any more time
#   on it than absolutely necessary.

###############################################################################

import commands, os, pg, re, sys, time
import apt_pkg
from daklib import database
from daklib import utils
from daklib.dak_exceptions import *

###############################################################################

re_arch_from_filename = re.compile(r"binary-[^/]+")

###############################################################################

Cnf = None
projectB = None
files_id_cache = {}
source_cache = {}
arch_all_cache = {}
binary_cache = {}
location_path_cache = {}
#
files_id_serial = 0
source_id_serial = 0
src_associations_id_serial = 0
dsc_files_id_serial = 0
files_query_cache = None
source_query_cache = None
src_associations_query_cache = None
dsc_files_query_cache = None
orig_tar_gz_cache = {}
#
binaries_id_serial = 0
binaries_query_cache = None
bin_associations_id_serial = 0
bin_associations_query_cache = None
#
source_cache_for_binaries = {}
reject_message = ""

################################################################################

def usage(exit_code=0):
    print """Usage: dak import-archive
Initializes a projectB database from an existing archive

  -a, --action              actually perform the initalization
  -h, --help                show this help and exit."""
    sys.exit(exit_code)

###############################################################################

def reject (str, prefix="Rejected: "):
    global reject_message
    if str:
        reject_message += prefix + str + "\n"

###############################################################################

def check_signature (filename):
    if not utils.re_taint_free.match(os.path.basename(filename)):
        reject("!!WARNING!! tainted filename: '%s'." % (filename))
        return None

    status_read, status_write = os.pipe()
    cmd = "gpgv --status-fd %s %s %s" \
          % (status_write, utils.gpg_keyring_args(), filename)
    (output, status, exit_status) = utils.gpgv_get_status_output(cmd, status_read, status_write)

    # Process the status-fd output
    keywords = {}
    bad = internal_error = ""
    for line in status.split('\n'):
        line = line.strip()
        if line == "":
            continue
        split = line.split()
        if len(split) < 2:
            internal_error += "gpgv status line is malformed (< 2 atoms) ['%s'].\n" % (line)
            continue
        (gnupg, keyword) = split[:2]
        if gnupg != "[GNUPG:]":
            internal_error += "gpgv status line is malformed (incorrect prefix '%s').\n" % (gnupg)
            continue
        args = split[2:]
        if keywords.has_key(keyword) and keyword != "NODATA" and keyword != "SIGEXPIRED":
            internal_error += "found duplicate status token ('%s').\n" % (keyword)
            continue
        else:
            keywords[keyword] = args

    # If we failed to parse the status-fd output, let's just whine and bail now
    if internal_error:
        reject("internal error while performing signature check on %s." % (filename))
        reject(internal_error, "")
        reject("Please report the above errors to the Archive maintainers by replying to this mail.", "")
        return None

    # Now check for obviously bad things in the processed output
    if keywords.has_key("SIGEXPIRED"):
        utils.warn("%s: signing key has expired." % (filename))
    if keywords.has_key("KEYREVOKED"):
        reject("key used to sign %s has been revoked." % (filename))
        bad = 1
    if keywords.has_key("BADSIG"):
        reject("bad signature on %s." % (filename))
        bad = 1
    if keywords.has_key("ERRSIG") and not keywords.has_key("NO_PUBKEY"):
        reject("failed to check signature on %s." % (filename))
        bad = 1
    if keywords.has_key("NO_PUBKEY"):
        args = keywords["NO_PUBKEY"]
        if len(args) < 1:
            reject("internal error while checking signature on %s." % (filename))
            bad = 1
        else:
            fingerprint = args[0]
    if keywords.has_key("BADARMOR"):
        reject("ascii armour of signature was corrupt in %s." % (filename))
        bad = 1
    if keywords.has_key("NODATA"):
        utils.warn("no signature found for %s." % (filename))
        return "NOSIG"
        #reject("no signature found in %s." % (filename))
        #bad = 1

    if bad:
        return None

    # Next check gpgv exited with a zero return code
    if exit_status and not keywords.has_key("NO_PUBKEY"):
        reject("gpgv failed while checking %s." % (filename))
        if status.strip():
            reject(utils.prefix_multi_line_string(status, " [GPG status-fd output:] "), "")
        else:
            reject(utils.prefix_multi_line_string(output, " [GPG output:] "), "")
        return None

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        if not keywords.has_key("NO_PUBKEY"):
            reject("signature on %s does not appear to be valid [No VALIDSIG]." % (filename))
            bad = 1
    else:
        args = keywords["VALIDSIG"]
        if len(args) < 1:
            reject("internal error while checking signature on %s." % (filename))
            bad = 1
        else:
            fingerprint = args[0]
    if not keywords.has_key("GOODSIG") and not keywords.has_key("NO_PUBKEY"):
        reject("signature on %s does not appear to be valid [No GOODSIG]." % (filename))
        bad = 1
    if not keywords.has_key("SIG_ID") and not keywords.has_key("NO_PUBKEY"):
        reject("signature on %s does not appear to be valid [No SIG_ID]." % (filename))
        bad = 1

    # Finally ensure there's not something we don't recognise
    known_keywords = utils.Dict(VALIDSIG="",SIG_ID="",GOODSIG="",BADSIG="",ERRSIG="",
                                SIGEXPIRED="",KEYREVOKED="",NO_PUBKEY="",BADARMOR="",
                                NODATA="")

    for keyword in keywords.keys():
        if not known_keywords.has_key(keyword):
            reject("found unknown status token '%s' from gpgv with args '%r' in %s." % (keyword, keywords[keyword], filename))
            bad = 1

    if bad:
        return None
    else:
        return fingerprint

################################################################################

# Prepares a filename or directory (s) to be file.filename by stripping any part of the location (sub) from it.
def poolify (s, sub):
    for i in xrange(len(sub)):
        if sub[i:] == s[0:len(sub)-i]:
            return s[len(sub)-i:]
    return s

def update_archives ():
    projectB.query("DELETE FROM archive")
    for archive in Cnf.SubTree("Archive").List():
        SubSec = Cnf.SubTree("Archive::%s" % (archive))
        projectB.query("INSERT INTO archive (name, origin_server, description) VALUES ('%s', '%s', '%s')"
                       % (archive, SubSec["OriginServer"], SubSec["Description"]))

def update_components ():
    projectB.query("DELETE FROM component")
    for component in Cnf.SubTree("Component").List():
        SubSec = Cnf.SubTree("Component::%s" % (component))
        projectB.query("INSERT INTO component (name, description, meets_dfsg) VALUES ('%s', '%s', '%s')" %
                       (component, SubSec["Description"], SubSec["MeetsDFSG"]))

def update_locations ():
    projectB.query("DELETE FROM location")
    for location in Cnf.SubTree("Location").List():
        SubSec = Cnf.SubTree("Location::%s" % (location))
        archive_id = database.get_archive_id(SubSec["archive"])
        type = SubSec.Find("type")
        if type == "legacy-mixed":
            projectB.query("INSERT INTO location (path, archive, type) VALUES ('%s', %d, '%s')" % (location, archive_id, SubSec["type"]))
        else:
            for component in Cnf.SubTree("Component").List():
                component_id = database.get_component_id(component)
                projectB.query("INSERT INTO location (path, component, archive, type) VALUES ('%s', %d, %d, '%s')" %
                               (location, component_id, archive_id, SubSec["type"]))

def update_architectures ():
    projectB.query("DELETE FROM architecture")
    for arch in Cnf.SubTree("Architectures").List():
        projectB.query("INSERT INTO architecture (arch_string, description) VALUES ('%s', '%s')" % (arch, Cnf["Architectures::%s" % (arch)]))

def update_suites ():
    projectB.query("DELETE FROM suite")
    for suite in Cnf.SubTree("Suite").List():
        SubSec = Cnf.SubTree("Suite::%s" %(suite))
        projectB.query("INSERT INTO suite (suite_name) VALUES ('%s')" % suite.lower())
        for i in ("Version", "Origin", "Description"):
            if SubSec.has_key(i):
                projectB.query("UPDATE suite SET %s = '%s' WHERE suite_name = '%s'" % (i.lower(), SubSec[i], suite.lower()))
        for architecture in Cnf.ValueList("Suite::%s::Architectures" % (suite)):
            architecture_id = database.get_architecture_id (architecture)
            projectB.query("INSERT INTO suite_architectures (suite, architecture) VALUES (currval('suite_id_seq'), %d)" % (architecture_id))

def update_override_type():
    projectB.query("DELETE FROM override_type")
    for type in Cnf.ValueList("OverrideType"):
        projectB.query("INSERT INTO override_type (type) VALUES ('%s')" % (type))

def update_priority():
    projectB.query("DELETE FROM priority")
    for priority in Cnf.SubTree("Priority").List():
        projectB.query("INSERT INTO priority (priority, level) VALUES ('%s', %s)" % (priority, Cnf["Priority::%s" % (priority)]))

def update_section():
    projectB.query("DELETE FROM section")
    for component in Cnf.SubTree("Component").List():
        if Cnf["Control-Overrides::ComponentPosition"] == "prefix":
            suffix = ""
            if component != 'main':
                prefix = component + '/'
            else:
                prefix = ""
        else:
            prefix = ""
            if component != 'main':
                suffix = '/' + component
            else:
                suffix = ""
        for section in Cnf.ValueList("Section"):
            projectB.query("INSERT INTO section (section) VALUES ('%s%s%s')" % (prefix, section, suffix))

def get_location_path(directory):
    global location_path_cache

    if location_path_cache.has_key(directory):
        return location_path_cache[directory]

    q = projectB.query("SELECT DISTINCT path FROM location WHERE path ~ '%s'" % (directory))
    try:
        path = q.getresult()[0][0]
    except:
        utils.fubar("[import-archive] get_location_path(): Couldn't get path for %s" % (directory))
    location_path_cache[directory] = path
    return path

################################################################################

def get_or_set_files_id (filename, size, md5sum, location_id):
    global files_id_cache, files_id_serial, files_query_cache

    cache_key = "_".join((filename, size, md5sum, repr(location_id)))
    if not files_id_cache.has_key(cache_key):
        files_id_serial += 1
        files_query_cache.write("%d\t%s\t%s\t%s\t%d\t\\N\n" % (files_id_serial, filename, size, md5sum, location_id))
        files_id_cache[cache_key] = files_id_serial

    return files_id_cache[cache_key]

###############################################################################

def process_sources (filename, suite, component, archive):
    global source_cache, source_query_cache, src_associations_query_cache, dsc_files_query_cache, source_id_serial, src_associations_id_serial, dsc_files_id_serial, source_cache_for_binaries, orig_tar_gz_cache, reject_message

    suite = suite.lower()
    suite_id = database.get_suite_id(suite)
    try:
        file = utils.open_file (filename)
    except CantOpenError:
        utils.warn("can't open '%s'" % (filename))
        return
    Scanner = apt_pkg.ParseTagFile(file)
    while Scanner.Step() != 0:
        package = Scanner.Section["package"]
        version = Scanner.Section["version"]
        directory = Scanner.Section["directory"]
        dsc_file = os.path.join(Cnf["Dir::Root"], directory, "%s_%s.dsc" % (package, utils.re_no_epoch.sub('', version)))
        # Sometimes the Directory path is a lie; check in the pool
        if not os.path.exists(dsc_file):
            if directory.split('/')[0] == "dists":
                directory = Cnf["Dir::PoolRoot"] + utils.poolify(package, component)
                dsc_file = os.path.join(Cnf["Dir::Root"], directory, "%s_%s.dsc" % (package, utils.re_no_epoch.sub('', version)))
        if not os.path.exists(dsc_file):
            utils.fubar("%s not found." % (dsc_file))
        install_date = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(dsc_file)))
        fingerprint = check_signature(dsc_file)
        fingerprint_id = database.get_or_set_fingerprint_id(fingerprint)
        if reject_message:
            utils.fubar("%s: %s" % (dsc_file, reject_message))
        maintainer = Scanner.Section["maintainer"]
        maintainer = maintainer.replace("'", "\\'")
        maintainer_id = database.get_or_set_maintainer_id(maintainer)
        location = get_location_path(directory.split('/')[0])
        location_id = database.get_location_id (location, component, archive)
        if not directory.endswith("/"):
            directory += '/'
        directory = poolify (directory, location)
        if directory != "" and not directory.endswith("/"):
            directory += '/'
        no_epoch_version = utils.re_no_epoch.sub('', version)
        # Add all files referenced by the .dsc to the files table
        ids = []
        for line in Scanner.Section["files"].split('\n'):
            id = None
            (md5sum, size, filename) = line.strip().split()
            # Don't duplicate .orig.tar.gz's
            if filename.endswith(".orig.tar.gz"):
                cache_key = "%s_%s_%s" % (filename, size, md5sum)
                if orig_tar_gz_cache.has_key(cache_key):
                    id = orig_tar_gz_cache[cache_key]
                else:
                    id = get_or_set_files_id (directory + filename, size, md5sum, location_id)
                    orig_tar_gz_cache[cache_key] = id
            else:
                id = get_or_set_files_id (directory + filename, size, md5sum, location_id)
            ids.append(id)
            # If this is the .dsc itself; save the ID for later.
            if filename.endswith(".dsc"):
                files_id = id
        filename = directory + package + '_' + no_epoch_version + '.dsc'
        cache_key = "%s_%s" % (package, version)
        if not source_cache.has_key(cache_key):
            nasty_key = "%s_%s" % (package, version)
            source_id_serial += 1
            if not source_cache_for_binaries.has_key(nasty_key):
                source_cache_for_binaries[nasty_key] = source_id_serial
            tmp_source_id = source_id_serial
            source_cache[cache_key] = source_id_serial
            source_query_cache.write("%d\t%s\t%s\t%d\t%d\t%s\t%s\n" % (source_id_serial, package, version, maintainer_id, files_id, install_date, fingerprint_id))
            for id in ids:
                dsc_files_id_serial += 1
                dsc_files_query_cache.write("%d\t%d\t%d\n" % (dsc_files_id_serial, tmp_source_id,id))
        else:
            tmp_source_id = source_cache[cache_key]

        src_associations_id_serial += 1
        src_associations_query_cache.write("%d\t%d\t%d\n" % (src_associations_id_serial, suite_id, tmp_source_id))

    file.close()

###############################################################################

def process_packages (filename, suite, component, archive):
    global arch_all_cache, binary_cache, binaries_id_serial, binaries_query_cache, bin_associations_id_serial, bin_associations_query_cache, reject_message

    count_total = 0
    count_bad = 0
    suite = suite.lower()
    suite_id = database.get_suite_id(suite)
    try:
        file = utils.open_file (filename)
    except CantOpenError:
        utils.warn("can't open '%s'" % (filename))
        return
    Scanner = apt_pkg.ParseTagFile(file)
    while Scanner.Step() != 0:
        package = Scanner.Section["package"]
        version = Scanner.Section["version"]
        maintainer = Scanner.Section["maintainer"]
        maintainer = maintainer.replace("'", "\\'")
        maintainer_id = database.get_or_set_maintainer_id(maintainer)
        architecture = Scanner.Section["architecture"]
        architecture_id = database.get_architecture_id (architecture)
        fingerprint = "NOSIG"
        fingerprint_id = database.get_or_set_fingerprint_id(fingerprint)
        if not Scanner.Section.has_key("source"):
            source = package
        else:
            source = Scanner.Section["source"]
        source_version = ""
        if source.find("(") != -1:
            m = utils.re_extract_src_version.match(source)
            source = m.group(1)
            source_version = m.group(2)
        if not source_version:
            source_version = version
        filename = Scanner.Section["filename"]
        location = get_location_path(filename.split('/')[0])
        location_id = database.get_location_id (location, component, archive)
        filename = poolify (filename, location)
        if architecture == "all":
            filename = re_arch_from_filename.sub("binary-all", filename)
        cache_key = "%s_%s" % (source, source_version)
        source_id = source_cache_for_binaries.get(cache_key, None)
        size = Scanner.Section["size"]
        md5sum = Scanner.Section["md5sum"]
        files_id = get_or_set_files_id (filename, size, md5sum, location_id)
        type = "deb"; # FIXME
        cache_key = "%s_%s_%s_%d_%d_%d_%d" % (package, version, repr(source_id), architecture_id, location_id, files_id, suite_id)
        if not arch_all_cache.has_key(cache_key):
            arch_all_cache[cache_key] = 1
            cache_key = "%s_%s_%s_%d" % (package, version, repr(source_id), architecture_id)
            if not binary_cache.has_key(cache_key):
                if not source_id:
                    source_id = "\N"
                    count_bad += 1
                else:
                    source_id = repr(source_id)
                binaries_id_serial += 1
                binaries_query_cache.write("%d\t%s\t%s\t%d\t%s\t%d\t%d\t%s\t%s\n" % (binaries_id_serial, package, version, maintainer_id, source_id, architecture_id, files_id, type, fingerprint_id))
                binary_cache[cache_key] = binaries_id_serial
                tmp_binaries_id = binaries_id_serial
            else:
                tmp_binaries_id = binary_cache[cache_key]

            bin_associations_id_serial += 1
            bin_associations_query_cache.write("%d\t%d\t%d\n" % (bin_associations_id_serial, suite_id, tmp_binaries_id))
            count_total += 1

    file.close()
    if count_bad != 0:
        print "%d binary packages processed; %d with no source match which is %.2f%%" % (count_total, count_bad, (float(count_bad)/count_total)*100)
    else:
        print "%d binary packages processed; 0 with no source match which is 0%%" % (count_total)

###############################################################################

def do_sources(sources, suite, component, server):
    temp_filename = utils.temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (sources, temp_filename))
    if (result != 0):
        utils.fubar("Gunzip invocation failed!\n%s" % (output), result)
    print 'Processing '+sources+'...'
    process_sources (temp_filename, suite, component, server)
    os.unlink(temp_filename)

###############################################################################

def do_da_do_da ():
    global Cnf, projectB, query_cache, files_query_cache, source_query_cache, src_associations_query_cache, dsc_files_query_cache, bin_associations_query_cache, binaries_query_cache

    Cnf = utils.get_conf()
    Arguments = [('a', "action", "Import-Archive::Options::Action"),
                 ('h', "help", "Import-Archive::Options::Help")]
    for i in [ "action", "help" ]:
        if not Cnf.has_key("Import-Archive::Options::%s" % (i)):
            Cnf["Import-Archive::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Import-Archive::Options")
    if Options["Help"]:
        usage()

    if not Options["Action"]:
        utils.warn("""no -a/--action given; not doing anything.
Please read the documentation before running this script.
""")
        usage(1)

    print "Re-Creating DB..."
    (result, output) = commands.getstatusoutput("psql -f init_pool.sql template1")
    if (result != 0):
        utils.fubar("psql invocation failed!\n", result)
    print output

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))

    database.init (Cnf, projectB)

    print "Adding static tables from conf file..."
    projectB.query("BEGIN WORK")
    update_architectures()
    update_components()
    update_archives()
    update_locations()
    update_suites()
    update_override_type()
    update_priority()
    update_section()
    projectB.query("COMMIT WORK")

    files_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"files","w")
    source_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"source","w")
    src_associations_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"src_associations","w")
    dsc_files_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"dsc_files","w")
    binaries_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"binaries","w")
    bin_associations_query_cache = utils.open_file(Cnf["Import-Archive::ExportDir"]+"bin_associations","w")

    projectB.query("BEGIN WORK")
    # Process Sources files to popoulate `source' and friends
    for location in Cnf.SubTree("Location").List():
        SubSec = Cnf.SubTree("Location::%s" % (location))
        server = SubSec["Archive"]
        type = Cnf.Find("Location::%s::Type" % (location))
        if type == "legacy-mixed":
            sources = location + 'Sources.gz'
            suite = Cnf.Find("Location::%s::Suite" % (location))
            do_sources(sources, suite, "",  server)
        elif type == "legacy" or type == "pool":
            for suite in Cnf.ValueList("Location::%s::Suites" % (location)):
                for component in Cnf.SubTree("Component").List():
                    sources = Cnf["Dir::Root"] + "dists/" + Cnf["Suite::%s::CodeName" % (suite)] + '/' + component + '/source/' + 'Sources.gz'
                    do_sources(sources, suite, component, server)
        else:
            utils.fubar("Unknown location type ('%s')." % (type))

    # Process Packages files to populate `binaries' and friends

    for location in Cnf.SubTree("Location").List():
        SubSec = Cnf.SubTree("Location::%s" % (location))
        server = SubSec["Archive"]
        type = Cnf.Find("Location::%s::Type" % (location))
        if type == "legacy-mixed":
            packages = location + 'Packages'
            suite = Cnf.Find("Location::%s::Suite" % (location))
            print 'Processing '+location+'...'
            process_packages (packages, suite, "", server)
        elif type == "legacy" or type == "pool":
            for suite in Cnf.ValueList("Location::%s::Suites" % (location)):
                for component in Cnf.SubTree("Component").List():
                    architectures = filter(utils.real_arch,
                                           Cnf.ValueList("Suite::%s::Architectures" % (suite)))
                    for architecture in architectures:
                        packages = Cnf["Dir::Root"] + "dists/" + Cnf["Suite::%s::CodeName" % (suite)] + '/' + component + '/binary-' + architecture + '/Packages'
                        print 'Processing '+packages+'...'
                        process_packages (packages, suite, component, server)

    files_query_cache.close()
    source_query_cache.close()
    src_associations_query_cache.close()
    dsc_files_query_cache.close()
    binaries_query_cache.close()
    bin_associations_query_cache.close()
    print "Writing data to `files' table..."
    projectB.query("COPY files FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"files"))
    print "Writing data to `source' table..."
    projectB.query("COPY source FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"source"))
    print "Writing data to `src_associations' table..."
    projectB.query("COPY src_associations FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"src_associations"))
    print "Writing data to `dsc_files' table..."
    projectB.query("COPY dsc_files FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"dsc_files"))
    print "Writing data to `binaries' table..."
    projectB.query("COPY binaries FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"binaries"))
    print "Writing data to `bin_associations' table..."
    projectB.query("COPY bin_associations FROM '%s'" % (Cnf["Import-Archive::ExportDir"]+"bin_associations"))
    print "Committing..."
    projectB.query("COMMIT WORK")

    # Add the constraints and otherwise generally clean up the database.
    # See add_constraints.sql for more details...

    print "Running add_constraints.sql..."
    (result, output) = commands.getstatusoutput("psql %s < add_constraints.sql" % (Cnf["DB::Name"]))
    print output
    if (result != 0):
        utils.fubar("psql invocation failed!\n%s" % (output), result)

    return

################################################################################

def main():
    utils.try_with_debug(do_da_do_da)

################################################################################

if __name__ == '__main__':
    main()
