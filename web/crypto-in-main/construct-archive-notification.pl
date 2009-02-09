#!/usr/bin/perl -w

# Usage: construct-notification packages_files


use vars qw (%sources);



$/ = "";
while (<>) {
  my @f = split(/^([a-z0-9]+):\s*/mi);
  shift @f;
  my %f = ();
  while (@f) {
    my $value = pop @f;
    my $field = pop @f;
    chomp $value;
    $f{lc $field} = $value;
  }
  $f{source} = $f{package} unless defined $f{source};
  $sources{$f{source}}{$f{package}} = $f{description};
}

foreach my $source (sort {$a cmp $b} keys %sources) {
  print "Source package: $source\n";
  foreach my $package (sort {$a cmp $b } keys %{$sources{$source}}) {
    print "Package: $package\n";
    print "Description: ";
    print $sources{$source}{$package};
    print "\n";
  }
  print "\n\n\n";
}
