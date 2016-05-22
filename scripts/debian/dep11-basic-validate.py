#!/usr/bin/env python3
#
# Copyright (C) 2015 Matthias Klumpp <mak@debian.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3.0 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program.

import os
import sys
import yaml
import gzip
import lzma
from voluptuous import Schema, Required, All, Any, Length, Range, Match, Url
from optparse import OptionParser

schema_header = Schema({
    Required('File'): All(str, 'DEP-11', msg="Must be \"DEP-11\""),
    Required('Origin'): All(str, Length(min=1)),
    Required('Version'): All(str, Match(r'(\d+\.?)+$'), msg="Must be a valid version number"),
    Required('MediaBaseUrl'): All(str, Url()),
    'Time': All(str),
    'Priority': All(int),
})

schema_translated = Schema({
    Required('C'): All(str, Length(min=1), msg="Must have an unlocalized 'C' key"),
    dict: All(str, Length(min=1)),
}, extra = True)

schema_component = Schema({
    Required('Type'): All(str, Length(min=1)),
    Required('ID'): All(str, Length(min=1)),
    Required('Name'): All(dict, Length(min=1), schema_translated),
    Required('Package'): All(str, Length(min=1)),
}, extra = True)

def add_issue(msg):
    print(msg)

def test_custom_objects(lines):
    ret = True
    for i in range(0, len(lines)):
        if "!!python/" in lines[i]:
            add_issue("Python object encoded in line %i." % (i))
            ret = False
    return ret

def is_quoted(s):
        return (s.startswith("\"") and s.endswith("\"")) or (s.startswith("\'") and s.endswith("\'"))

def test_localized_dict(doc, ldict, id_string):
    ret = True
    for lang, value in ldict.items():
        if lang == 'x-test':
            add_issue("[%s][%s]: %s" % (doc['ID'], id_string, "Found cruft locale: x-test"))
        if lang == 'xx':
            add_issue("[%s][%s]: %s" % (doc['ID'], id_string, "Found cruft locale: xx"))
        if lang.endswith('.UTF-8'):
            add_issue("[%s][%s]: %s" % (doc['ID'], id_string, "AppStream locale names should not specify encoding (ends with .UTF-8)"))
        if is_quoted(value):
            add_issue("[%s][%s]: %s" % (doc['ID'], id_string, "String is quoted: '%s' @ %s" % (value, lang)))
        if " " in lang:
            add_issue("[%s][%s]: %s" % (doc['ID'], id_string, "Locale name contains space: '%s'" % (lang)))
            # this - as opposed to the other issues - is an error
            ret = False
    return ret

def test_localized(doc, key):
    ldict = doc.get(key, None)
    if not ldict:
        return True

    return test_localized_dict(doc, ldict, key)

def validate_data(data):
        ret = True
        lines = data.split("\n")

        # see if there are any Python-specific objects encoded
        ret = test_custom_objects(lines)

        try:
            docs = yaml.safe_load_all(data)
            header = next(docs)
        except Exception as e:
            add_issue("Could not parse file: %s" % (str(e)))
            return False

        try:
            schema_header(header)
        except Exception as e:
            add_issue("Invalid DEP-11 header: %s" % (str(e)))
            ret = False

        for doc in docs:
            docid = doc.get('ID')
            pkgname = doc.get('Package')
            if not pkgname:
                pkgname = "?unknown?"
            if not doc:
                add_issue("FATAL: Empty document found.")
                ret = False
                continue
            if not docid:
                add_issue("FATAL: Component without ID found.")
                ret = False
                continue

            try:
                schema_component(doc)
            except Exception as e:
                add_issue("[%s]: %s" % (docid, str(e)))
                ret = False
                continue

            # more tests for the icon key
            icon = doc.get('Icon')
            if (doc['Type'] == "desktop-app") or (doc['Type'] == "web-app"):
                if not doc.get('Icon'):
                    add_issue("[%s]: %s" % (docid, "Components containing an application must have an 'Icon' key."))
                    ret = False
            if icon:
                if (not icon.get('stock')) and (not icon.get('cached')) and (not icon.get('local')):
                    add_issue("[%s]: %s" % (docid, "A 'stock', 'cached' or 'local' icon must at least be provided. @ data['Icon']"))
                    ret = False

            if not test_localized(doc, 'Name'):
                ret = False
            if not test_localized(doc, 'Summary'):
                ret = False
            if not test_localized(doc, 'Description'):
                ret = False
            if not test_localized(doc, 'DeveloperName'):
                ret = False

            for shot in doc.get('Screenshots', list()):
                caption = shot.get('caption')
                if caption:
                    if not test_localized_dict(doc, caption, "Screenshots.x.caption"):
                        ret = False

        return ret

def validate_file(fname):
    f = None
    if fname.endswith(".gz"):
        f = gzip.open(fname, 'r')
    elif fname.endswith(".xz"):
        f = lzma.open(fname, 'r')
    else:
        f = open(fname, 'r')

    data = str(f.read(), 'utf-8')
    f.close()

    return validate_data(data)

def validate_dir(dirname):
    ret = True
    for root, subfolders, files in os.walk(dirname):
        for fname in files:
            fpath = os.path.join(root, fname)
            if os.path.islink(fpath):
                add_issue("FATAL: Symlinks are not allowed")
                return False
            if fname.endswith(".yml.gz") or fname.endswith(".yml.xz"):
                if not validate_file(fpath):
                    ret = False

    return ret

def main():
    parser = OptionParser()

    (options, args) = parser.parse_args()

    if len(args) < 1:
        print("You need to specify a file to validate!")
        sys.exit(4)
    fname = args[0]

    if os.path.isdir(fname):
        ret = validate_dir(fname)
    elif os.path.islink(fname):
        add_issue("FATAL: Symlinks are not allowed")
        ret = False
    else:
        ret = validate_file(fname)
    if ret:
        msg = "DEP-11 basic validation successful."
    else:
        msg = "DEP-11 validation failed!"
    print(msg)

    if not ret:
        sys.exit(1)

if __name__ == "__main__":
    main()
