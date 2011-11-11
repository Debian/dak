#! /usr/bin/perl

#    removals - generate an RSS feed of removals from Debian
#    (C) Copyright 2005 Tollef Fog Heen <tfheen@err.no>
#    (C) Copyright 2010 Uli Martens <uli@youam.net>
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

die "usage: $0 <configfile>\n" unless scalar @ARGV;

my $config;

my $cfgfname = $ARGV[0];
open my $cfgfile, "<", $cfgfname
	or die "config file $cfgfname not found: $!\n";
while (<$cfgfile>){
	chomp;
	s/#.*//;
	next if m/^$/;
	my ($key, $val) = split ": ", $_, 2;
	warn "$0: warning: redefining config key $key\n" if defined $config->{$key};
	$config->{$key} = $val;
}
close $cfgfile;

for ( qw/input items title link description subject creator publisher rights language/ ) {
	die "config option '$_' missing in $cfgfname\n" unless $config->{$_};
}
open REMOVALS, "<", $config->{input};

my @removals;

{
  local $/ = "=========================================================================\n=========================================================================";
  @removals = reverse <REMOVALS>;
}

my $rss = new XML::RSS (version => '1.0');
$rss->channel(
			  title        => $config->{title},
			  link         => $config->{link},
			  description  => $config->{description},
			  dc => {
					 date       => POSIX::strftime ("%FT%R+00:00",gmtime()),
					 subject    => $config->{subject},
					 creator    => $config->{creator},
					 publisher  => $config->{publisher},
					 rights     => $config->{rights},
					 language   => $config->{language},
					},
			  syn => {
					  updatePeriod     => "hourly",
					  updateFrequency  => "1",
					  updateBase       => "1901-01-01T00:00+00:00",
					 }
			 );

my $num_to_display = $config->{items};
for my $removal (@removals ) {
  my ($null, $date, $ftpmaster, $body, $packages, $reason);
  $removal =~ s/=========================================================================//g;
  $removal =~ m/\[Date: ([^]]+)\] \[ftpmaster: ([^]]+)\]/;
  $date = $1;
  $ftpmaster = $2;
  ($null, $body) = split /\n/, $removal, 2;
  chomp $body;
  $body =~ m/---- Reason ---.*\n(.*)/;
  $reason = $1;
  $packages = join( ", ",
    map { ( my $p = $_ ) =~ s/^\s*(.+?) \|.+/$1/; $p }
    grep {/.+\|.+\|.+/} split( /\n/, $body ) );
  $packages
    = ( substr $packages, 0,
    ( $config->{titlelength} - length($reason) - 6 ) )
    . " ..."
    if length("$packages: $reason") > $config->{titlelength};
  my $link =  encode_base64($date . $ftpmaster);
  chomp($link);

  $rss->add_item(title       => "$packages: $reason",
				 link        => $config->{link} . "?" . $link,
				 description => qq[<pre>$body</pre>],
				 dc => {
						creator => "$ftpmaster",
					   }
				);

  $num_to_display -= 1;
  last unless $num_to_display;
}
print $rss->as_string;
