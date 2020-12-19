#! /usr/bin/env python3
#
# Copyright (C) 2014, Ansgar Burchardt <ansgar@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from base_test import DakTestCase
import unittest
from daklib.packagelist import PackageList


class FakeArchitecture(object):
    def __init__(self, name):
        self.arch_string = name


class FakeSuite(object):
    def __init__(self, *architectures):
        self.architectures = [FakeArchitecture(a) for a in architectures]


source_all = {
    'Package-List': '\n libdune-common-doc deb doc optional arch=all\n',
    'Binary': 'libdune-common-doc\n',
    }

source_any = {
    'Package-List': '\n libdune-common-dev deb libdevel optional arch=any\n',
    'Binary': 'libdune-common-dev\n',
    }

source_all_any = {
    'Package-List': '\n libdune-common-dev deb libdevel optional arch=any\nlibdune-common-doc deb doc optional arch=all\n',
    'Binary': 'libdune-common-dev, libdune-common-doc\n',
    }

source_amd64 = {
    'Package-List': '\n libdune-common-dev deb libdevel optional arch=amd64\n',
    'Binary': 'libdune-common-dev\n',
    }

source_linuxany = {
    'Package-List': '\n libdune-common-dev deb libdevel optional arch=linux-any\n',
    'Binary': 'libdune-common-dev\n',
    }

source_noarch = {
    'Package-List': '\n libdune-common-dev deb libdevel optional\n',
    'Binary': 'libdune-common-dev\n',
}

source_fallback = {
    'Binary': 'libdune-common-dev\n',
}

source_profiles = {
    'Package-List':
    '\n pkg-a deb misc optional arch=any profile=!stage1'
    '\n pkg-b deb misc optional arch=any profile=!stage1,!stage2'
    '\n pkg-c deb misc optional arch=any profile=stage1'
    '\n pkg-d deb misc optional arch=any profile=stage1,stage2'
    '\n pkg-e deb misc optional arch=any profile=stage1+stage2'
    '\n pkg-f deb misc optional arch=any profile=!stage1+!stage2'
    '\n pkg-g deb misc optional arch=any profile=!stage1+stage2'
    '\n pkg-h deb misc optional arch=any profile=stage1+!stage2'
    '\n',
    'Binary': 'pkg-a, pkg-b, pkg-c, pkg-d, pkg-e, pkg-f, pkg-g, pkg-h\n',
}


class TestPackageList(DakTestCase):
    def testArchAll(self):
        pl = PackageList(source_all)

        self.assertTrue(pl.has_arch_indep_packages())
        self.assertFalse(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 0)

        suite_all = FakeSuite('all')
        p_all = pl.packages_for_suite(suite_all)
        self.assertEqual(len(p_all), 1)

        suite_all_amd64 = FakeSuite('amd64', 'all')
        p_all_amd64 = pl.packages_for_suite(suite_all_amd64)
        self.assertEqual(len(p_all_amd64), 1)

        p = p_all[0]
        self.assertEqual(p.name, 'libdune-common-doc')
        self.assertEqual(p.type, 'deb')
        self.assertEqual(p.section, 'doc')
        self.assertEqual(p.component, 'main')
        self.assertEqual(p.priority, 'optional')
        self.assertEqual(p.architectures, ['all'])

    def testArchAny(self):
        pl = PackageList(source_any)

        self.assertFalse(pl.has_arch_indep_packages())
        self.assertTrue(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

        suite_all = FakeSuite('all')
        p_all = pl.packages_for_suite(suite_all)
        self.assertEqual(len(p_all), 0)

        suite_all_amd64 = FakeSuite('amd64', 'all')
        p_all_amd64 = pl.packages_for_suite(suite_all_amd64)
        self.assertEqual(len(p_all_amd64), 1)

    def testArchAnyAll(self):
        pl = PackageList(source_all_any)

        self.assertTrue(pl.has_arch_indep_packages())
        self.assertTrue(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

        suite_amd64_i386 = FakeSuite('amd64', 'i386')
        p_amd64_i386 = pl.packages_for_suite(suite_amd64_i386)
        self.assertEqual(len(p_amd64_i386), 1)

        suite_all = FakeSuite('all')
        p_all = pl.packages_for_suite(suite_all)
        self.assertEqual(len(p_all), 1)

        suite_all_amd64 = FakeSuite('amd64', 'all')
        p_all_amd64 = pl.packages_for_suite(suite_all_amd64)
        self.assertEqual(len(p_all_amd64), 2)

    def testArchAmd64(self):
        pl = PackageList(source_amd64)

        self.assertFalse(pl.has_arch_indep_packages())
        self.assertTrue(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

        suite_i386 = FakeSuite('i386')
        p_i386 = pl.packages_for_suite(suite_i386)
        self.assertEqual(len(p_i386), 0)

    def testArchLinuxAny(self):
        pl = PackageList(source_linuxany)

        self.assertFalse(pl.has_arch_indep_packages())
        self.assertTrue(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

        suite_i386 = FakeSuite('i386')
        p_i386 = pl.packages_for_suite(suite_i386)
        self.assertEqual(len(p_i386), 1)

        suite_kfreebsdi386 = FakeSuite('kfreebsd-i386')
        p_kfreebsdi386 = pl.packages_for_suite(suite_kfreebsdi386)
        self.assertEqual(len(p_kfreebsdi386), 0)

        suite_source = FakeSuite('source')
        p_source = pl.packages_for_suite(suite_source)
        self.assertEqual(len(p_source), 0)

    def testNoArch(self):
        pl = PackageList(source_noarch)

        self.assertIsNone(pl.has_arch_indep_packages())
        self.assertIsNone(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

    def testFallback(self):
        pl = PackageList(source_fallback)

        self.assertIsNone(pl.has_arch_indep_packages())
        self.assertIsNone(pl.has_arch_dep_packages())

        suite_amd64 = FakeSuite('amd64')
        p_amd64 = pl.packages_for_suite(suite_amd64)
        self.assertEqual(len(p_amd64), 1)

    def testProfiles(self):
        pl = PackageList(source_profiles)

        self.assertEqual(len(pl.package_list), 8)

        built_in_default_profile = {'pkg-a', 'pkg-b', 'pkg-f', 'pkg-g', 'pkg-h'}
        not_built_in_default_profile = {'pkg-c', 'pkg-d', 'pkg-e'}

        for entry in pl.package_list:
            if entry.built_in_default_profile():
                self.assertIn(entry.name, built_in_default_profile)
            else:
                self.assertIn(entry.name, not_built_in_default_profile)

        suite_amd64 = FakeSuite('amd64')
        ps_only_default = pl.packages_for_suite(suite_amd64)
        ps_all = pl.packages_for_suite(suite_amd64, only_default_profile=False)
        self.assertSetEqual({p.name for p in ps_only_default}, built_in_default_profile)
        self.assertSetEqual({p.name for p in ps_all}, built_in_default_profile | not_built_in_default_profile)


if __name__ == '__main__':
    unittest.main()
