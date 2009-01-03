import sys, os, textwrap

import apt_pkg
import daklib.utils, daklib.database
import syck

import daklib.extensions
from daklib.extensions import replace_dak_function

def check_transition():
    changes = dak_module.changes
    reject = dak_module.reject
    Cnf = dak_module.Cnf

    sourcepkg = changes["source"]

    # No sourceful upload -> no need to do anything else, direct return
    # We also work with unstable uploads, not experimental or those going to some
    # proposed-updates queue
    if "source" not in changes["architecture"] or "unstable" not in changes["distribution"]:
        return

    # Also only check if there is a file defined (and existant) with
    # checks.
    transpath = Cnf.get("Dinstall::Reject::ReleaseTransitions", "")
    if transpath == "" or not os.path.exists(transpath):
        return

    # Parse the yaml file
    sourcefile = file(transpath, 'r')
    sourcecontent = sourcefile.read()
    try:
        transitions = syck.load(sourcecontent)
    except syck.error, msg:
        # This shouldn't happen, there is a wrapper to edit the file which
        # checks it, but we prefer to be safe than ending up rejecting
        # everything.
        daklib.utils.warn("Not checking transitions, the transitions file is broken: %s." % (msg))
        return

    # Now look through all defined transitions
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        current = daklib.database.get_suite_version(source, "testing")
        if current is not None:
            compare = apt_pkg.VersionCompare(current, expected)

        if current is None or compare < 0:
            # This is still valid, the current version in testing is older than
            # the new version we wait for, or there is none in testing yet

            # Check if the source we look at is affected by this.
            if sourcepkg in t['packages']:
                # The source is affected, lets reject it.

                rejectmsg = "%s: part of the %s transition.\n\n" % (
                    sourcepkg, trans)

                if current is not None:
                    currentlymsg = "at version %s" % (current)
                else:
                    currentlymsg = "not present in testing"

                rejectmsg += "Transition description: %s\n\n" % (t["reason"])

                rejectmsg += "\n".join(textwrap.wrap("""Your package
is part of a testing transition designed to get %s migrated (it is
currently %s, we need version %s).  This transition is managed by the
Release Team, and %s is the Release-Team member responsible for it.
Please mail debian-release@lists.debian.org or contact %s directly if you
need further assistance.  You might want to upload to experimental until this
transition is done."""
                        % (source, currentlymsg, expected,t["rm"], t["rm"])))

                reject(rejectmsg + "\n")
                return

@replace_dak_function("process-unchecked", "check_signed_by_key")
def check_signed_by_key(oldfn):
    changes = dak_module.changes
    reject = dak_module.reject

    if changes["source"] == "dpkg":
        fpr = changes["fingerprint"]
        (uid, uid_name, is_dm) = dak_module.lookup_uid_from_fingerprint(fpr)
        if fpr == "5906F687BD03ACAD0D8E602EFCF37657" or uid == "iwj":
            reject("Upload blocked due to hijack attempt 2008/03/19")

            # NB: 1.15.0, 1.15.2 signed by this key targetted at unstable
            #     have been made available in the wild, and should remain
            #     blocked until Debian's dpkg has revved past those version
            #     numbers

    oldfn()

    check_transition()
