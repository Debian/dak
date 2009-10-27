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

class FormatThree(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(native\)'

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat

    format = r'3\.\d+ \(quilt\)'
