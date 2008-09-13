#!/bin/bash
#
# Fetches latest copy of pseudo-packages
# Joerg Jaspert <joerg@debian.org>

. vars

cd ${scriptdir}/masterfiles

echo Updating archive version of pseudo-packages
for file in maintainers description; do
	wget -t2 -T20 -q -N http://bugs.debian.org/pseudopackages/pseudo-packages.${file} || echo "Some error occured with $file..."
done
