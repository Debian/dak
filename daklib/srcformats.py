import re

srcformats = []

class SourceFormat(type):
    def __new__(cls, name, bases, attrs):
        klass = super(SourceFormat, cls).__new__(cls, name, bases, attrs)
        srcformats.append(klass)

        assert str(klass.name)
        klass.re_format = re.compile(klass.format)

        return klass

class FormatOne(object):
    __metaclass__ = SourceFormat

    name = '1.0'
    format = r'1.0'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not (native_tar_gz or (orig_tar_gz and debian_diff)):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if (orig_tar_gz != orig_tar) or \
           (native_tar_gz != native_tar) or \
           debian_tar or more_orig_tar:
            yield "contains source files not allowed in format %s" % cls.name

class FormatThree(object):
    __metaclass__ = SourceFormat

    name = '3.x (native)'
    format = r'3\.\d+ \(native\)'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not native_tar:
            yield "lack of required files for format %s" % cls.name
        if orig_tar or debian_diff or debian_tar or more_orig_tar:
            yield "contains source files not allowed in format %s" % cls.name

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat

    name = '3.x (quilt)'
    format = r'3\.\d+ \(quilt\)'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not(orig_tar and debian_tar):
            yield "lack of required files for format %s" % cls.name
        if debian_diff or native_tar:
            yield "contains source files not allowed in format %s" % cls.name
