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
            yield m.groupdict()

def generate_reject_messages(parsed_tags, tag_definitions, log=lambda *args: args):
    """
    Generates package reject messages by comparing parsed lintian output with
    tag definitions. Returns a generator containing the reject messages.
    """

    tags = set()
    for values in tag_definitions.values():
        for tag_name in values:
            tags.add(tag_name)

    for tag in parsed_tags:
        tag_name = tag['tag']

        if tag_name not in tags:
            continue

        # Was tag overridden?
        if tag['level'] == 'O':

            if tag_name in tag_definitions['nonfatal']:
                # Overriding this tag is allowed.
                pass

            elif tag_name in tag_definitions['fatal']:
                # Overriding this tag is NOT allowed.

                log('ftpmaster does not allow tag to be overridable', tag_name)
                yield "%(package)s: Overriden tag %(tag)s found, but this " \
                    "tag may not be overridden." % tag

        else:
            # Tag is known and not overridden; reject
            yield "%(package)s: lintian output: '%(tag)s %(description)s', " \
                "automatically rejected package." % tag

            # Now tell if they *might* override it.
            if tag_name in tag_definitions['nonfatal']:
                log("auto rejecting", "overridable", tag_name)
                yield "%(package)s: If you have a good reason, you may " \
                   "override this lintian tag." % tag
            else:
                log("auto rejecting", "not overridable", tag_name)
