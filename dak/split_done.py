#!/usr/bin/env python

# Copyright (C) 2004, 2005, 2006  James Troup <james@nocrew.org>

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

import glob, os, stat, time
import daklib.utils

################################################################################

def main():
    Cnf = daklib.utils.get_conf()
    count = 0
    move_date = int(time.time())-(30*84600)
    os.chdir(Cnf["Dir::Queue::Done"])
    files = glob.glob("%s/*" % (Cnf["Dir::Queue::Done"]))
    for filename in files:
        if os.path.isfile(filename):
            filemtime = os.stat(filename)[stat.ST_MTIME]
            if filemtime > move_date:
                continue
            mtime = time.gmtime(filemtime)
            dirname = time.strftime("%Y/%m/%d", mtime)
            if not os.path.exists(dirname):
                print "Creating: %s" % (dirname)
                os.makedirs(dirname)
            dest = dirname + '/' + os.path.basename(filename)
            if os.path.exists(dest):
                daklib.utils.fubar("%s already exists." % (dest))
            print "Move: %s -> %s" % (filename, dest)
            os.rename(filename, dest)
            count = count + 1
    print "Moved %d files." % (count)

############################################################

if __name__ == '__main__':
    main()
