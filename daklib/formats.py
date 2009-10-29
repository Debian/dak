from regexes import re_verwithext
from dak_exceptions import UnknownFormatError

def parse_format(txt):
    """
    Parse a .changes Format string into a tuple representation for easy
    comparison.

    >>> parse_format('1.0')
    (1, 0)
    >>> parse_format('8.4 (hardy)')
    (8, 4, 'hardy')

    If the format doesn't match these forms, raises UnknownFormatError.
    """

    format = re_verwithext.search(txt)

    if format is None:
        raise UnknownFormatError, txt

    format = format.groups()

    if format[1] is None:
        format = int(float(format[0])), 0, format[2]
    else:
        format = int(format[0]), int(format[1]), format[2]

    if format[2] is None:
        format = format[:2]

    return format

def validate_changes_format(format, field):
    """
    Validate a tuple-representation of a .changes Format: field. Raises
    UnknownFormatError if the field is invalid, otherwise return type is
    undefined.
    """

    if (format < (1, 5) or format > (1, 8)):
        raise UnknownFormatError, repr(format)

    if field != 'files' and format < (1, 8):
        raise UnknownFormatError, repr(format)
