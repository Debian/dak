#!/usr/bin/env python

# Logging functions
# Copyright (C) 2001, 2002  James Troup <james@nocrew.org>
# $Id: logging.py,v 1.3 2002-10-16 02:47:32 troup Exp $

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

import os, pwd, time;
import utils;

################################################################################

class Logger:
    "Logger object"
    Cnf = None;
    logfile = None;
    program = None;

    def __init__ (self, Cnf, program):
        "Initialize a new Logger object"
        self.Cnf = Cnf;
        self.program = program;
        # Create the log directory if it doesn't exist
        logdir = Cnf["Dir::Log"];
        if not os.path.exists(logdir):
            umask = os.umask(00000);
            os.makedirs(logdir, 02775);
        # Open the logfile
        logfilename = "%s/%s" % (logdir, time.strftime("%Y-%m"));
        logfile = utils.open_file(logfilename, 'a');
        # Seek to the end of the logfile
        logfile.seek(0,2);
        self.logfile = logfile;
        # Log the start of the program
        user = pwd.getpwuid(os.getuid())[0];
        self.log(["program start", user]);

    def log (self, details):
        "Log an event"
        # Prepend the timestamp and program name
        details.insert(0, self.program);
        timestamp = time.strftime("%Y%m%d%H%M%S");
        details.insert(0, timestamp);
        # Force the contents of the list to be string.join-able
        details = map(str, details);
        # Write out the log in TSV
        self.logfile.write("~".join(details)+'\n');
        # Flush the output to enable tail-ing
        self.logfile.flush();

    def close (self):
        "Close a Logger object"
        self.log(["program end"]);
        self.logfile.flush();
        self.logfile.close();
