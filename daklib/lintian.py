from regexes import re_parse_lintian

def parse_lintian_output(output):
    for line in output.split('\n'):
        m = re_parse_lintian.match(line)
        if m:
            yield m.groups()
