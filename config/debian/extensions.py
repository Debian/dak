import sys, os

import daklib.extensions
from daklib.extensions import replace_dak_function

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


