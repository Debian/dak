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
