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
    def reject_msgs(cls, has):
        if not (has['native_tar_gz'] or (has['orig_tar_gz'] and has['debian_diff'])):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if (has['orig_tar_gz'] != has['orig_tar']) or \
           (has['native_tar_gz'] != has['native_tar']) or \
           has['debian_tar'] or has['more_orig_tar']:
            yield "contains source files not allowed in format %s" % cls.name

class FormatThree(object):
    __metaclass__ = SourceFormat

    name = '3.x (native)'
    format = r'3\.\d+ \(native\)'

    @classmethod
    def reject_msgs(cls, has):
        if not has['native_tar']:
            yield "lack of required files for format %s" % cls.name
        if has['orig_tar'] or has['debian_diff'] or has['debian_tar'] or has['more_orig_tar']:
            yield "contains source files not allowed in format %s" % cls.name

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat

    name = '3.x (quilt)'
    format = r'3\.\d+ \(quilt\)'

    @classmethod
    def reject_msgs(cls, has):
        if not (has['orig_tar'] and has['debian_tar']):
            yield "lack of required files for format %s" % cls.name
        if has['debian_diff'] or has['native_tar']:
            yield "contains source files not allowed in format %s" % cls.name
