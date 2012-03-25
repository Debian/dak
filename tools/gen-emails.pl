#!/usr/bin/perl

# Copyright (C) 2010 Alexander Wirt <formorer@debian.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <http://www.gnu.org/licenses/>.

use warnings;
use strict;
use DBI;

my $outfile = shift;

if (! $outfile) {
	print "Output Filename needed\n";
	exit 1;
}

my $dbh = DBI->connect("DBI:Pg:dbname=backports");


my $sth = $dbh->prepare( "
	SELECT 	maintainer.name,
		source.source,
		max(source.version)
	FROM 	source,source_suite,
		maintainer
	WHERE 	source.id = source_suite.src
	AND	source.changedby = maintainer.id
	AND	( suite_name = 'squeeze-backports' )
	GROUP BY source.source,maintainer.name;
");

if ( !defined $sth ) {
	die "Cannot prepare statement: $DBI::errstr\n";
}

$sth->execute or die "Could not execute query: $DBI::errstr\n";

open (my $fh, '>', $outfile) or die "Could not open File $outfile for writing: $!";

while (my $row = $sth->fetchrow_hashref) {
	my $email;
	if ($row->{'name'} =~ /<([^>]+)>/) {
		$email = $1;
	} else {
		next;
	}
	printf($fh "%s: %s\n", $row->{'source'}, $email);
}

close($fh);

