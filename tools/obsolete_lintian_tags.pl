#!/usr/bin/perl
#
# Generates a list of obsolete lintian autoreject tags
# (C) 2012 Niels Thykier <nthykier@debian.org>
# (C) 2012 Luca Falavigna <dktrkranz@debian.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# 02111-1307 USA


use strict;
use warnings;

BEGIN {
    $ENV{'LINTIAN_ROOT'} = '/usr/share/lintian'
        unless defined $ENV{'LINTIAN_ROOT'};
};

use Getopt::Long;
use lib "$ENV{'LINTIAN_ROOT'}/lib";
use Lintian::Profile;

my $profile = Lintian::Profile->new ('debian');
my @lintian_tags = (sort $profile->tags(1));
my $autoreject_tags = '../config/debian/lintian.tags';

open (LINTIAN, $autoreject_tags) or die ('Could not open lintian tags file.');
foreach my $tag (<LINTIAN>) {
    if ($tag =~ m/\s+- \S+/) {
        $tag =~ s/\s+- //;
        chomp $tag;
        print "$tag\n" if not grep (/^$tag$/i, @lintian_tags);
    }
}
close (LINTIAN);

exit 0;
