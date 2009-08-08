#!/bin/sh

# regexp to test if a file is okay:
#  grep -Ev '^[a-z0-9A-Z.+-]+\   Task    [a-z0-9:. ,+-]+$' task*

x="build-essential tag task"
opath="/org/ftp.debian.org/scripts/override"

for s in squeeze sid; do
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

