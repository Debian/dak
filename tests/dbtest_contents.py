#! /usr/bin/env python3

from db_test import DBDakTestCase, fixture

from daklib.dbconn import *
from daklib.contents import BinaryContentsWriter, BinaryContentsScanner, \
    UnpackedSource, SourceContentsScanner, SourceContentsWriter

from os.path import normpath
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import FlushError
from subprocess import CalledProcessError
import unittest


class ContentsTestCase(DBDakTestCase):

    """
    This TestCase checks the behaviour of contents generation.
    """

    def test_duplicates1(self):
        '''
        Test the BinContents class for duplication problems.
        '''
        self.setup_binaries()
        contents1 = BinContents(file='usr/bin/hello',
                                binary=self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        self.session.flush()
        # test duplicates
        contents2 = BinContents(file='usr/bin/hello',
                                binary=self.binary['hello_2.2-1_i386'])
        self.session.add(contents2)
        self.assertRaises(FlushError, self.session.flush)

    def test_duplicates2(self):
        '''
        Test the BinContents class for more duplication problems.
        '''
        self.setup_binaries()
        contents1 = BinContents(file='usr/bin/hello',
                                binary=self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        contents2 = BinContents(file='usr/bin/gruezi',
                                binary=self.binary['hello_2.2-1_i386'])
        self.session.add(contents2)
        self.session.flush()
        # test duplicates
        contents2.file = 'usr/bin/hello'
        self.assertRaises(IntegrityError, self.session.flush)

    def test_duplicates3(self):
        '''
        Test the BinContents class even more.
        '''
        self.setup_binaries()
        contents1 = BinContents(file='usr/bin/hello',
                                binary=self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        # same file in different binary packages should be okay
        contents2 = BinContents(file='usr/bin/hello',
                                binary=self.binary['gnome-hello_2.2-1_i386'])
        self.session.add(contents2)
        self.session.flush()

    def test_overridetype(self):
        '''
        Test the OverrideType class.
        '''
        self.setup_overridetypes()
        self.assertEqual('deb', self.otype['deb'].overridetype)
        self.assertEqual(0, self.otype['deb'].overrides.count())
        self.assertEqual(
            self.otype['deb'], get_override_type('deb', self.session))

    def test_section(self):
        '''
        Test Section class.
        '''
        self.setup_sections()
        self.assertEqual('python', self.section['python'].section)
        self.assertEqual('python', self.section['python'])
        self.assertTrue(self.section['python'] != 'java')
        self.assertEqual(
            self.section['python'], get_section('python', self.session))
        all_sections = get_sections(self.session)
        self.assertEqual(
            self.section['python'].section_id, all_sections['python'])
        self.assertEqual(0, self.section['python'].overrides.count())

    def test_priority(self):
        '''
        Test Priority class.
        '''
        self.setup_priorities()
        self.assertEqual('standard', self.prio['standard'].priority)
        self.assertEqual(3, self.prio['standard'].level)
        self.assertEqual('standard', self.prio['standard'])
        self.assertTrue(self.prio['standard'] != 'extra')
        self.assertEqual(
            self.prio['standard'], get_priority('standard', self.session))
        all_priorities = get_priorities(self.session)
        self.assertEqual(
            self.prio['standard'].priority_id, all_priorities['standard'])
        self.assertEqual(0, self.prio['standard'].overrides.count())

    def test_override(self):
        '''
        Test Override class.
        '''
        self.setup_overrides()
        list = get_override('hello', session=self.session)
        self.assertEqual(3, len(list))
        self.assertTrue(self.override['hello_sid_main_udeb'] in list)
        self.assertTrue(self.override['hello_squeeze_main_deb'] in list)
        list = get_override('hello', suite='sid', session=self.session)
        self.assertEqual([self.override['hello_sid_main_udeb']], list)
        list = get_override('hello', suite=['sid'], session=self.session)
        self.assertEqual([self.override['hello_sid_main_udeb']], list)
        list = get_override('hello', component='contrib', session=self.session)
        self.assertEqual([self.override['hello_lenny_contrib_deb']], list)
        list = get_override(
            'hello', component=['contrib'], session=self.session)
        self.assertEqual([self.override['hello_lenny_contrib_deb']], list)
        list = get_override('hello', overridetype='deb', session=self.session)
        self.assertEqual(2, len(list))
        self.assertTrue(self.override['hello_sid_main_udeb'] not in list)
        self.assertTrue(self.override['hello_squeeze_main_deb'] in list)
        list = get_override(
            'hello', overridetype=['deb'], session=self.session)
        self.assertEqual(2, len(list))
        self.assertTrue(self.override['hello_sid_main_udeb'] not in list)
        self.assertTrue(self.override['hello_squeeze_main_deb'] in list)
        # test the backrefs
        self.assertEqual(self.override['hello_sid_main_udeb'],
                         self.suite['sid'].overrides.one())
        self.assertEqual(2, self.comp['main'].overrides.count())
        self.assertEqual(self.override['hello_sid_main_udeb'],
                         self.comp['main'].overrides.filter_by(suite=self.suite['sid']).one())
        self.assertEqual(self.override['hello_sid_main_udeb'],
                         self.otype['udeb'].overrides.one())

    def test_binarycontentswriter(self):
        '''
        Test the BinaryContentsWriter class.
        '''
        self.setup_binaries()
        self.setup_overrides()
        self.binary['hello_2.2-1_i386'].contents.append(
            BinContents(file='/usr/bin/hello'))
        self.session.flush()
        cw = BinaryContentsWriter(self.suite['squeeze'], self.arch['i386'],
                                  self.otype['deb'], self.comp['main'])
        self.assertEqual(
            ['/usr/bin/hello                                          python/hello\n'],
            cw.get_list())
        # test formatline and sort order
        self.assertEqual(
            '/usr/bin/hello                                          python/hello\n',
            cw.formatline('/usr/bin/hello', 'python/hello'))
        # test unicode support
        self.binary['hello_2.2-1_i386'].contents.append(
            BinContents(file='\xc3\xb6'))
        self.session.flush()


if __name__ == '__main__':
    unittest.main()
