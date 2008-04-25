# tl_CHECK_TOOL_PREFIX will work _BEFORE_ AC_CANONICAL_HOST, etc., has been
# called. It should be called again after these have been called.
#
# Basically we want to check if the host alias specified by the user is
# different from the build alias. The rules work like this:-
#
# If host is not specified, it defaults to NONOPT
# If build is not specified, it defaults to NONOPT
# If nonopt is not specified, we guess all other values

