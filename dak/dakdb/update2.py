#!/usr/bin/env python
# coding=utf8

"""
debversion

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
@copyright: 2008  Roger Leigh <rleigh@debian.org>
@license: GNU General Public License version 2 or later
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError

################################################################################

def do_update(self):
    print "Note: to be able to enable the the PL/Perl (plperl) procedural language, we do"
    print "need postgresql-plperl-$postgres-version installed. Make sure that this is the"
    print "case before you continue. Interrupt if it isn't, sleeping 5 seconds now."
    print "(We need to be database superuser for this to work!)"
    time.sleep (5)

    try:
        c = self.db.cursor()

        print "Enabling PL/Perl language"
        c.execute("CREATE LANGUAGE plperl;")
        c.execute("CREATE LANGUAGE plpgsql;")

        print "Adding debversion type to database."

# Not present in all databases, maybe PL/Perl version-dependent?
#        c.execute("SET SESSION plperl.use_strict TO 't';")

        c.execute("CREATE DOMAIN debversion AS TEXT;")
        c.execute("COMMENT ON DOMAIN debversion IS 'Debian package version number';")

        c.execute("""ALTER DOMAIN debversion
                     ADD CONSTRAINT debversion_syntax
                     CHECK (VALUE !~ '[^-+:.0-9a-zA-Z~]');""")

        # From Dpkg::Version::parseversion
        c.execute("""CREATE OR REPLACE FUNCTION debversion_split (debversion)
  RETURNS text[] AS $$
    my $ver = shift;
    my %verhash;
    if ($ver =~ /:/)
    {
        $ver =~ /^(\d+):(.+)/ or die "bad version number '$ver'";
        $verhash{epoch} = $1;
        $ver = $2;
    }
    else
    {
        $verhash{epoch} = 0;
    }
    if ($ver =~ /(.+)-(.*)$/)
    {
        $verhash{version} = $1;
        $verhash{revision} = $2;
    }
    else
    {
        $verhash{version} = $ver;
        $verhash{revision} = 0;
    }

    return [$verhash{'epoch'}, $verhash{'version'}, $verhash{'revision'}];
$$
  LANGUAGE plperl
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_split (debversion)
                   IS 'Split debian version into epoch, upstream version and revision';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_epoch (version debversion)
  RETURNS text AS $$
DECLARE
  split text[];
BEGIN
  split := debversion_split(version);
  RETURN split[1];
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;
COMMENT ON FUNCTION debversion_epoch (debversion)
  IS 'Get debian version epoch';

CREATE OR REPLACE FUNCTION debversion_version (version debversion)
  RETURNS text AS $$
DECLARE
  split text[];
BEGIN
  split := debversion_split(version);
  RETURN split[2];
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_version (debversion)
                   IS 'Get debian version upstream version';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_revision (version debversion)
  RETURNS text AS $$
DECLARE
  split text[];
BEGIN
  split := debversion_split(version);
  RETURN split[3];
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_revision (debversion)
                   IS 'Get debian version revision';""")

# From Dpkg::Version::parseversion
        c.execute("""CREATE OR REPLACE FUNCTION debversion_compare_single (version1 text, version2 text)
  RETURNS integer AS $$
     sub order{
	  my ($x) = @_;
	  ##define order(x) ((x) == '~' ? -1 \
	  #           : cisdigit((x)) ? 0 \
	  #           : !(x) ? 0 \
	  #           : cisalpha((x)) ? (x) \
	  #           : (x) + 256)
	  # This comparison is out of dpkg's order to avoid
	  # comparing things to undef and triggering warnings.
	  if (not defined $x or not length $x) {
	       return 0;
	  }
	  elsif ($x eq '~') {
	       return -1;
	  }
	  elsif ($x =~ /^\d$/) {
	       return 0;
	  }
	  elsif ($x =~ /^[A-Z]$/i) {
	       return ord($x);
	  }
	  else {
	       return ord($x) + 256;
	  }
     }

     sub next_elem(\@){
	  my $a = shift;
	  return @{$a} ? shift @{$a} : undef;
     }
     my ($val, $ref) = @_;
     $val = "" if not defined $val;
     $ref = "" if not defined $ref;
     my @val = split //,$val;
     my @ref = split //,$ref;
     my $vc = next_elem @val;
     my $rc = next_elem @ref;
     while (defined $vc or defined $rc) {
	  my $first_diff = 0;
	  while ((defined $vc and $vc !~ /^\d$/) or
		 (defined $rc and $rc !~ /^\d$/)) {
	       my $vo = order($vc); my $ro = order($rc);
	       # Unlike dpkg's verrevcmp, we only return 1 or -1 here.
	       return (($vo - $ro > 0) ? 1 : -1) if $vo != $ro;
	       $vc = next_elem @val; $rc = next_elem @ref;
	  }
	  while (defined $vc and $vc eq '0') {
	       $vc = next_elem @val;
	  }
	  while (defined $rc and $rc eq '0') {
	       $rc = next_elem @ref;
	  }
	  while (defined $vc and $vc =~ /^\d$/ and
		 defined $rc and $rc =~ /^\d$/) {
	       $first_diff = ord($vc) - ord($rc) if !$first_diff;
	       $vc = next_elem @val; $rc = next_elem @ref;
	  }
	  return 1 if defined $vc and $vc =~ /^\d$/;
	  return -1 if defined $rc and $rc =~ /^\d$/;
	  return (($first_diff  > 0) ? 1 : -1) if $first_diff;
     }
     return 0;
$$
  LANGUAGE plperl
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_compare_single (text, text)
                   IS 'Compare upstream or revision parts of Debian versions';""")

# Logic only derived from Dpkg::Version::parseversion
        c.execute("""CREATE OR REPLACE FUNCTION debversion_compare (version1 debversion, version2 debversion)
  RETURNS integer AS $$
DECLARE
  split1 text[];
  split2 text[];
  result integer;
BEGIN
  result := 0;
  split1 := debversion_split(version1);
  split2 := debversion_split(version2);

  -- RAISE NOTICE 'Version 1: %', version1;
  -- RAISE NOTICE 'Version 2: %', version2;
  -- RAISE NOTICE 'Split 1: %', split1;
  -- RAISE NOTICE 'Split 2: %', split2;

  IF split1[1] > split2[1] THEN
    result := 1;
  ELSIF split1[1] < split2[1] THEN
    result := -1;
  ELSE
    result := debversion_compare_single(split1[2], split2[2]);
    IF result = 0 THEN
      result := debversion_compare_single(split1[3], split2[3]);
    END IF;
  END IF;

  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_compare (debversion, debversion)
  IS 'Compare Debian versions';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_eq (version1 debversion, version2 debversion)
  RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp = 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_eq (debversion, debversion)
  IS 'debversion equal';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_ne (version1 debversion, version2 debversion)
  RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp <> 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_ne (debversion, debversion)
  IS 'debversion not equal';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_lt (version1 debversion, version2 debversion)
  RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp < 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_lt (debversion, debversion)
                   IS 'debversion less-than';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_gt (version1 debversion, version2 debversion) RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp > 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_gt (debversion, debversion)
                   IS 'debversion greater-than';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_le (version1 debversion, version2 debversion)
  RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp <= 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_le (debversion, debversion)
                   IS 'debversion less-than-or-equal';""")

        c.execute("""CREATE OR REPLACE FUNCTION debversion_ge (version1 debversion, version2 debversion)
  RETURNS boolean AS $$
DECLARE
  comp integer;
  result boolean;
BEGIN
  comp := debversion_compare(version1, version2);
  result := comp >= 0;
  RETURN result;
END;
$$
  LANGUAGE plpgsql
  IMMUTABLE STRICT;""")
        c.execute("""COMMENT ON FUNCTION debversion_ge (debversion, debversion)
                   IS 'debversion greater-than-or-equal';""")

        c.execute("""CREATE OPERATOR = (
                   PROCEDURE = debversion_eq,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = =,
                   NEGATOR = !=);""")
        c.execute("""COMMENT ON OPERATOR = (debversion, debversion)
                   IS 'debversion equal';""")

        c.execute("""CREATE OPERATOR != (
                   PROCEDURE = debversion_eq,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = !=,
                   NEGATOR = =);""")
        c.execute("""COMMENT ON OPERATOR != (debversion, debversion)
                   IS 'debversion not equal';""")

        c.execute("""CREATE OPERATOR < (
                   PROCEDURE = debversion_lt,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = >,
                   NEGATOR = >=);""")
        c.execute("""COMMENT ON OPERATOR < (debversion, debversion)
                   IS 'debversion less-than';""")

        c.execute("""CREATE OPERATOR > (
                   PROCEDURE = debversion_gt,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = <,
                   NEGATOR = >=);""")
        c.execute("""COMMENT ON OPERATOR > (debversion, debversion)
                   IS 'debversion greater-than';""")

        c.execute("""CREATE OPERATOR <= (
                   PROCEDURE = debversion_le,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = >=,
                   NEGATOR = >);""")
        c.execute("""COMMENT ON OPERATOR <= (debversion, debversion)
                   IS 'debversion less-than-or-equal';""")

        c.execute("""CREATE OPERATOR >= (
                   PROCEDURE = debversion_ge,
                   LEFTARG = debversion,
                   RIGHTARG = debversion,
                   COMMUTATOR = <=,
                   NEGATOR = <);""")
        c.execute("""COMMENT ON OPERATOR >= (debversion, debversion)
                   IS 'debversion greater-than-or-equal';""")

        c.execute("ALTER TABLE source ALTER COLUMN version TYPE debversion;")
        c.execute("ALTER TABLE binaries ALTER COLUMN version TYPE debversion;")

        c.execute("UPDATE config SET value = '2' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy debversion updates, rollback issued. Error message : %s" % (str(msg)))
