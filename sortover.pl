#!/usr/bin/perl
%iv=qw(required 00
       important 01
       standard 02
       optional 03
       extra 04);
sub t {
    return $_[0] if $_[0] =~ m/^\#/;
    $_[0] =~ m/^(\S+)\s+(\S+)\s+(\S+)\s/ || die "$0: `$_[0]'";
    return "$3 $iv{$2} $1";
}
print(sort { &t($a) cmp &t($b) } <STDIN>) || die $!;
close(STDOUT) || die $!;
