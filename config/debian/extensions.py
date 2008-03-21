import sys, os, textwrap

import apt_pkg
import daklib.utils, daklib.database
import syck

# This function and its data should move into daklib/extensions.py
# or something.
replaced_funcs = {}
replace_funcs = {}
def replace_dak_function(module,name):
    def x(f):
        def myfunc(*a,**kw):
	    global replaced_funcs
            f(replaced_funcs[name], *a, **kw)
	myfunc.__name__ = f.__name__
	myfunc.__doc__ = f.__doc__
	myfunc.__dict__.update(f.__dict__)

        replace_funcs["%s:%s" % (module,name)] = myfunc
	return f
    return x

def check_transition():
    changes = dak_module.changes
    reject = dak_module.reject
    Cnf = dak_module.Cnf

    sourcepkg = changes["source"]

    # No sourceful upload -> no need to do anything else, direct return
    if "source" not in changes["architecture"]:
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
need further assistance."""
			% (source, currentlymsg, expected,t["rm"], t["rm"])))

                reject(rejectmsg + "\n")
                return

@replace_dak_function("process-unchecked", "check_signed_by_key")
def check_signed_by_key(oldfn):
    changes = dak_module.changes
    reject = dak_module.reject

    if changes["source"] == "dpkg":
        fpr = changes["fingerprint"]
        (uid, uid_name) = dak_module.lookup_uid_from_fingerprint(fpr)
        if fpr == "5906F687BD03ACAD0D8E602EFCF37657" or uid == "iwj":
            reject("Upload blocked due to hijack attempt 2008/03/19")

	    # NB: 1.15.0, 1.15.2 signed by this key targetted at unstable
	    #     have been made available in the wild, and should remain
	    #     blocked until Debian's dpkg has revved past those version
	    #     numbers

    oldfn()

    check_transition()

def init(name):
    global replaced_funcs

    # This bit should be done automatically too
    replaced_funcs = {}
    for f,newfunc in replace_funcs.iteritems():
        m,f = f.split(":",1)
        if len(f) > 0 and m == name:
	    replaced_funcs[f] = dak_module.__dict__[f]
	    dak_module.__dict__[f] = newfunc

