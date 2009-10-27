import re

srcformats = []

class SourceFormat(type):
    def __new__(cls, name, bases, attrs):
        klass = super(SourceFormat, cls).__new__(cls, name, bases, attrs)
        srcformats.append(klass)

        klass.re_format = re.compile(klass.format)

        return klass

class FormatOne(object):
    __metaclass__ = SourceFormat

    format = r'1.0'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not (native_tar_gz or (orig_tar_gz and debian_diff)):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if (orig_tar_gz != orig_tar) or \
           (native_tar_gz != native_tar) or \
           debian_tar or more_orig_tar:
            yield "contains source files not allowed in format 1.0"

class FormatThree(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(native\)'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not native_tar:
            yield "lack required files for format 3.x (native)."
        if orig_tar or debian_diff or debian_tar or more_orig_tar:
            yield "contains source files not allowed in format '3.x (native)'"

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(quilt\)'

    @classmethod
    def reject_msgs(cls, native_tar, native_tar_gz, debian_tar, debian_diff, orig_tar, orig_tar_gz, more_orig_tar):
        if not(orig_tar and debian_tar):
            yield "lack required files for format '3.x (quilt)'."
        if debian_diff or native_tar:
            yield "contains source files not allowed in format 3.x (quilt)"
