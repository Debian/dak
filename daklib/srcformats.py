import re

from dak_exceptions import UnknownFormatError

srcformats = []

def get_format_from_string(txt):
    """
    Returns the SourceFormat class that corresponds to the specified .changes
    Format value. If the string does not match any class, UnknownFormatError
    is raised.
    """

    for format in srcformats:
        if format.re_format.match(txt):
            return format

    raise UnknownFormatError, "Unknown format %r" % txt

class SourceFormat(type):
    def __new__(cls, name, bases, attrs):
        klass = super(SourceFormat, cls).__new__(cls, name, bases, attrs)
        srcformats.append(klass)

        assert str(klass.name)
        assert iter(klass.requires)
        assert iter(klass.disallowed)

        klass.re_format = re.compile(klass.format)

        return klass

    @classmethod
    def reject_msgs(cls, has):
        if len(cls.requires) != len([x for x in cls.requires if has[x]]):
            yield "lack of required files for format %s" % cls.name

        for key in cls.disallowed:
            if has[key]:
                yield "contains source files not allowed in format %s" % cls.name

    @classmethod
    def validate_format(cls, format, is_a_dsc=False, field='files'):
        """
        Raises UnknownFormatError if the specified format tuple is not valid for
        this format (for example, the format (1, 0) is not valid for the
        "3.0 (quilt)" format). Return value is undefined in all other cases.
        """
        pass

class FormatOne(SourceFormat):
    __metaclass__ = SourceFormat

    name = '1.0'
    format = r'1.0'

    requires = ()
    disallowed = ('debian_tar', 'more_orig_tar')

    @classmethod
    def reject_msgs(cls, has):
        if not (has['native_tar_gz'] or (has['orig_tar_gz'] and has['debian_diff'])):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if has['native_tar_gz'] and has['debian_diff']:
            yield "native package with diff makes no sense"
        if (has['orig_tar_gz'] != has['orig_tar']) or \
           (has['native_tar_gz'] != has['native_tar']):
            yield "contains source files not allowed in format %s" % cls.name

        for msg in super(FormatOne, cls).reject_msgs(has):
            yield msg

    @classmethod
    def validate_format(cls, format, is_a_dsc=False, field='files'):
        msg = "Invalid format %s definition: %r" % (cls.name, format)

        if is_a_dsc:
            if format != (1, 0):
                raise UnknownFormatError, msg
        else:
            if (format < (1,5) or format > (1,8)):
                raise UnknownFormatError, msg
            if field != "files" and format < (1,8):
                raise UnknownFormatError, msg

class FormatThree(SourceFormat):
    __metaclass__ = SourceFormat

    name = '3.x (native)'
    format = r'3\.\d+ \(native\)'

    requires = ('native_tar',)
    disallowed = ('orig_tar', 'debian_diff', 'debian_tar', 'more_orig_tar')

    @classmethod
    def validate_format(cls, format, **kwargs):
        if format != (3, 0, 'native'):
            raise UnknownFormatError, "Invalid format %s definition: %r" % \
                (cls.name, format)

class FormatThreeQuilt(SourceFormat):
    __metaclass__ = SourceFormat

    name = '3.x (quilt)'
    format = r'3\.\d+ \(quilt\)'

    requires = ('orig_tar', 'debian_tar')
    disallowed = ('debian_diff', 'native_tar')

    @classmethod
    def validate_format(cls, format, **kwargs):
        if format != (3, 0, 'quilt'):
            raise UnknownFormatError, "Invalid format %s definition: %r" % \
                (cls.name, format)
