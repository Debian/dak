from regexes import re_parse_lintian

def parse_lintian_output(output):
    """
    Parses Lintian output and returns a generator with the data.

    >>> list(parse_lintian_output('W: pkgname: some-tag path/to/file'))
    [('W', 'pkgname', 'some-tag', 'path/to/file')]
    """

    for line in output.split('\n'):
        m = re_parse_lintian.match(line)
        if m:
            yield m.groups()

def generate_reject_messages(parsed_tags, tag_definitions, log=lambda *args: args):
    """
    Generates package reject messages by comparing parsed lintian output with
    tag definitions. Returns a generator containing the reject messages.
    """

    tags = set()
    for values in tag_definitions.values():
        for tag in values:
            tags.add(tag)

    for etype, epackage, etag, etext in parsed_tags:
        if etag not in tags:
            continue

        # Was tag overridden?
        if etype == 'O':

            if etag in tag_definitions['nonfatal']:
                # Overriding this tag is allowed.
                pass

            elif etag in tag_definitions['fatal']:
                # Overriding this tag is NOT allowed.

                log('ftpmaster does not allow tag to be overridable', etag)
                yield "%s: Overriden tag %s found, but this tag " \
                    "may not be overridden." % (epackage, etag)

        else:
            # Tag is known and not overridden; reject
            yield "%s: Found lintian output: '%s %s', automatically " \
                "rejected package." % (epackage, etag, etext)

            # Now tell if they *might* override it.
            if etag in tag_definitions['nonfatal']:
                log("auto rejecting", "overridable", etag)
                yield "%s: If you have a good reason, you may override this " \
                   "lintian tag." % epackage
            else:
                log("auto rejecting", "not overridable", etag)
