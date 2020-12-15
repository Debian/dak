"""parse Package-List field

@copyright: 2014, Ansgar Burchardt <ansgar@debian.org>
@license: GPL-2+
"""

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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from daklib.architecture import match_architecture
from daklib.utils import extract_component_from_section


class InvalidSource(Exception):
    pass


class PackageListEntry(object):
    def __init__(self, name, package_type, section, component, priority, **other):
        self.name = name
        self.type = package_type
        self.section = section
        self.component = component
        self.priority = priority
        self.other = other

        self.architectures = self._architectures()

    def _architectures(self):
        archs = self.other.get("arch", None)
        if archs is None:
            return None
        return archs.split(',')

    def built_on_architecture(self, architecture):
        archs = self.architectures
        if archs is None:
            return None
        for arch in archs:
            if match_architecture(architecture, arch):
                return True
        return False

    def built_in_suite(self, suite):
        built = False
        for arch in suite.architectures:
            if arch.arch_string == 'source':
                continue
            built_on_arch = self.built_on_architecture(arch.arch_string)
            if built_on_arch:
                return True
            if built_on_arch is None:
                built = None
        return built

    def built_in_default_profile(self):
        # See man:dsc(5) and https://bugs.debian.org/913965#77
        profiles_and = self.other.get('profile')
        if profiles_and is None:
            return True
        return all(
            any(profile.startswith("!") for profile in profiles_or.split("+"))
            for profiles_or in profiles_and.split(",")
        )


class PackageList(object):
    def __init__(self, source):
        if 'Package-List' in source:
            self._parse(source)
        elif 'Binary' in source:
            self._parse_fallback(source)
        else:
            raise InvalidSource('Source package has neither Package-List nor Binary field.')

        self.fallback = any(entry.architectures is None for entry in self.package_list)

    def _binaries(self, source):
        return set(name.strip() for name in source['Binary'].split(","))

    def _parse(self, source):
        self.package_list = []

        binaries_binary = self._binaries(source)
        binaries_package_list = set()

        for line in source['Package-List'].split("\n"):
            if not line:
                continue
            fields = line.split()
            if len(fields) < 4:
                raise InvalidSource("Package-List entry has less than four fields.")

            # <name> <type> <component/section> <priority> [arch=<arch>[,<arch>]...]
            name = fields[0]
            package_type = fields[1]
            section, component = extract_component_from_section(fields[2])
            priority = fields[3]
            other = dict(kv.split('=', 1) for kv in fields[4:])

            if name in binaries_package_list:
                raise InvalidSource("Package-List has two entries for '{0}'.".format(name))
            if name not in binaries_binary:
                raise InvalidSource("Package-List lists {0} which is not listed in Binary.".format(name))
            binaries_package_list.add(name)

            entry = PackageListEntry(name, package_type, section, component, priority, **other)
            self.package_list.append(entry)

        if len(binaries_binary) != len(binaries_package_list):
            raise InvalidSource("Package-List and Binaries fields have a different number of entries.")

    def _parse_fallback(self, source):
        self.package_list = []

        for binary in self._binaries(source):
            name = binary
            package_type = None
            component = None
            section = None
            priority = None
            other = dict()

            entry = PackageListEntry(name, package_type, section, component, priority, **other)
            self.package_list.append(entry)

    def packages_for_suite(self, suite, only_default_profile=True):
        packages = []
        for entry in self.package_list:
            if only_default_profile and not entry.built_in_default_profile():
                continue
            built = entry.built_in_suite(suite)
            if built or built is None:
                packages.append(entry)
        return packages

    def has_arch_indep_packages(self):
        has_arch_indep = False
        for entry in self.package_list:
            built = entry.built_on_architecture('all')
            if built:
                return True
            if built is None:
                has_arch_indep = None
        return has_arch_indep

    def has_arch_dep_packages(self):
        has_arch_dep = False
        for entry in self.package_list:
            built_on_all = entry.built_on_architecture('all')
            if built_on_all is False:
                return True
            if built_on_all is None:
                has_arch_dep = None
        return has_arch_dep
