#!/bin/sh

# regexp to test if a file is okay:
#  grep -Ev '^[a-z0-9A-Z.+-]+\   Task    [a-z0-9:. ,+-]+$' task*

x="build-essential tag task"
opath="/org/ftp.debian.org/scripts/override"
apath="/org/ftp.debian.org/ftp/dists"

if [ ! -d "$apath" ]; then
  echo "$0: invalid path to archive" >&2
  exit 1
elif [ ! -L "$apath/testing" ]; then
  echo "$0: symlink for testing suite does not exist >&2"
  exit 1
fi

codename_testing="$(basename "$(readlink "$apath/testing")")"
if [ -z "$codename_testing" ] || [ ! -d "$apath/$codename_testing" ]; then
  echo "$0: invalid codename for testing suite ('$codename_testing')" >&2
  exit 1
fi

for s in "$codename_testing" sid; do
  for c in main contrib non-free; do
    echo "Making $opath/override.$s.extra.$c"
    if [ "$c" = "main" ]; then
      c2="";
    else
      c2=".$c"
    fi
    for t in $x; do
      if [ -e "$t$c2" ]; then cat $t$c2; fi
      if [ -e "$t.$s$c2" ]; then cat $t.$s$c2; fi
    done | sort > $opath/override.$s.extra.$c
  done
done

