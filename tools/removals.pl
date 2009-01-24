#! /usr/bin/perl

#    removals - generate an RSS feed of removals from Debian
#    (C) Copyright 2005 Tollef Fog Heen <tfheen@err.no>
#
#    This program is free software; you can redistribute it and/or
#    modify it under the terms of the GNU General Public License
#    version 2 as published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
#    02111-1307 USA


use strict;
use warnings;

use MIME::Base64 qw(encode_base64);
use XML::RSS;
use POSIX qw(strftime);
use CGI qw/:standard/;

open REMOVALS, "</srv/ftp.debian.org/web/removals.txt";

my @removals;

{
  local $/ = "=========================================================================\n=========================================================================";
  @removals = reverse <REMOVALS>;
}

my $rss = new XML::RSS (version => '1.0');
$rss->channel(
			  title        => "Removals from Debian",
			  link         => "http://ftp-master.debian.org/removals.txt",
			  description  => "List of all the removals from Debian's archives",
			  dc => {
					 date       => POSIX::strftime ("%FT%R+00:00",gmtime()),
					 subject    => "Removals from Debian",
					 creator    => 'tfheen@debian.org',
					 publisher  => 'joerg@debian.org',
					 rights     => 'Copyright 2005, Tollef Fog Heen',
					 language   => 'en-us',
					},
			  syn => {
					  updatePeriod     => "hourly",
					  updateFrequency  => "1",
					  updateBase       => "1901-01-01T00:00+00:00",
					 }
			 );

my $num_to_display = 16;
for my $removal (@removals ) {
  my ($null, $date, $ftpmaster, $body, $reason);
  $removal =~ s/=========================================================================//g;
  $removal =~ m/\[Date: ([^]]+)\] \[ftpmaster: ([^]]+)\]/;
  $date = $1;
  $ftpmaster = $2;
  ($null, $body) = split /\n/, $removal, 2;
  chomp $body;
  $body =~ m/---- Reason ---.*\n(.*)/;
  $reason = $1;
  my $link =  encode_base64($date . $ftpmaster);
  chomp($link);

  $rss->add_item(title       => "$reason",
				 link        => "http://ftp-master.debian.org/removals.txt?" . $link,
				 description => qq[&lt;pre&gt;$body&lt;/pre&gt;],
				 dc => {
						creator => "$ftpmaster",
					   }
				);

  $num_to_display -= 1;
  last unless $num_to_display;
}
print $rss->as_string;
