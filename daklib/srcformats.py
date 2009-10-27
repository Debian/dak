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
    def reject_msgs(cls, has_native_tar, has_native_tar_gz, has_debian_tar, has_debian_diff, has_orig_tar, has_orig_tar_gz, has_more_orig_tar):
        if not (has_native_tar_gz or (has_orig_tar_gz and has_debian_diff)):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if (has_orig_tar_gz != has_orig_tar) or \
           (has_native_tar_gz != has_native_tar) or \
           has_debian_tar or has_more_orig_tar:
            yield "contains source files not allowed in format 1.0"

class FormatThree(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(native\)'

    @classmethod
    def reject_msgs(cls, has_native_tar, has_native_tar_gz, has_debian_tar, has_debian_diff, has_orig_tar, has_orig_tar_gz, has_more_orig_tar):
        if not has_native_tar:
            yield "lack required files for format 3.x (native)."
        if has_orig_tar or has_debian_diff or has_debian_tar or has_more_orig_tar:
            yield "contains source files not allowed in format '3.x (native)'"

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(quilt\)'

    @classmethod
    def reject_msgs(cls, has_native_tar, has_native_tar_gz, has_debian_tar, has_debian_diff, has_orig_tar, has_orig_tar_gz, has_more_orig_tar):
        if not(has_orig_tar and has_debian_tar):
            yield "lack required files for format '3.x (quilt)'."
        if has_debian_diff or has_native_tar:
            yield "contains source files not allowed in format 3.x (quilt)"
