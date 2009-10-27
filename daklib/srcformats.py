srcformats = []

class SourceFormat(type):
    def __new__(cls, name, bases, attrs):
        klass = super(SourceFormat, cls).__new__(cls, name, bases, attrs)
        srcformats.append(klass)

        return klass

class FormatOne(object):
    __metaclass__ = SourceFormat

class FormatThree(object):
    __metaclass__ = SourceFormat

class FormatThreeQuilt(object):
    __metaclass__ = SourceFormat
