#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, BinContents, OverrideType, get_override_type, \
    Section, get_section, get_sections, Priority, get_priority, get_priorities

from sqlalchemy.exc import FlushError, IntegrityError
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
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        self.session.flush()
        # test duplicates
        contents2 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents2)
        self.assertRaises(FlushError, self.session.flush)

    def test_duplicates2(self):
        '''
        Test the BinContents class for more duplication problems.
        '''
        self.setup_binaries()
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        contents2 = BinContents(file = 'usr/bin/gruezi', \
            binary = self.binary['hello_2.2-1_i386'])
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
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        # same file in different binary packages should be okay
        contents2 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['gnome-hello_2.2-1_i386'])
        self.session.add(contents2)
        self.session.flush()

    def test_overridetype(self):
        '''
        Test the OverrideType class.
        '''
        debtype = OverrideType(overridetype = 'deb')
        self.session.add(debtype)
        self.session.flush()
        self.assertEqual('deb', debtype.overridetype)
        self.assertEqual(0, debtype.overrides.count())
        self.assertEqual(debtype, get_override_type('deb', self.session))

    def test_section(self):
        '''
        Test Section class.
        '''
        section = Section(section = 'python')
        self.session.add(section)
        self.session.flush()
        self.assertEqual('python', section.section)
        self.assertEqual('python', section)
        self.assertTrue(section != 'java')
        self.assertEqual(section, get_section('python', self.session))
        all_sections = get_sections(self.session)
        self.assertEqual(section.section_id, all_sections['python'])
        self.assertEqual(0, section.overrides.count())

    def test_priority(self):
        '''
        Test Priority class.
        '''
        priority = Priority(priority = 'standard', level = 7)
        self.session.add(priority)
        self.session.flush()
        self.assertEqual('standard', priority.priority)
        self.assertEqual(7, priority.level)
        self.assertEqual('standard', priority)
        self.assertTrue(priority != 'extra')
        self.assertEqual(priority, get_priority('standard', self.session))
        all_priorities = get_priorities(self.session)
        self.assertEqual(priority.priority_id, all_priorities['standard'])
        self.assertEqual(0, priority.overrides.count())

if __name__ == '__main__':
    unittest.main()
