"""Utilities for signed files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
@license: GNU General Public License version 2 or later
"""

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

import apt_pkg
import datetime
import errno
import fcntl
import os
import select

try:
    _MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    _MAXFD = 256

class GpgException(Exception):
    pass

class _Pipe(object):
    """context manager for pipes

    Note: When the pipe is closed by other means than the close_r and close_w
    methods, you have to set self.r (self.w) to None.
    """
    def __enter__(self):
        (self.r, self.w) = os.pipe()
        return self
    def __exit__(self, type, value, traceback):
        self.close_w()
        self.close_r()
        return False
    def close_r(self):
        """close reading side of the pipe"""
        if self.r:
            os.close(self.r)
            self.r = None
    def close_w(self):
        """close writing part of the pipe"""
        if self.w:
            os.close(self.w)
            self.w = None

class SignedFile(object):
    """handle files signed with PGP

    The following attributes are available:
      contents            - string with the content (after removing PGP armor)
      valid               - Boolean indicating a valid signature was found
      fingerprint         - fingerprint of the key used for signing
      primary_fingerprint - fingerprint of the primary key associated to the key used for signing
    """
    def __init__(self, data, keyrings, require_signature=True, gpg="/usr/bin/gpg"):
        """
        @param data: string containing the message
        @param keyrings: sequence of keyrings
        @param require_signature: if True (the default), will raise an exception if no valid signature was found
        @param gpg: location of the gpg binary
        """
        self.gpg = gpg
        self.keyrings = keyrings

        self.valid = False
        self.fingerprint = None
        self.primary_fingerprint = None

        self._verify(data, require_signature)

    def _verify(self, data, require_signature):
        with _Pipe() as stdin:
         with _Pipe() as contents:
          with _Pipe() as status:
           with _Pipe() as stderr:
            pid = os.fork()
            if pid == 0:
                self._exec_gpg(stdin.r, contents.w, stderr.w, status.w)
            else:
                stdin.close_r()
                contents.close_w()
                stderr.close_w()
                status.close_w()

                read = self._do_io([contents.r, stderr.r, status.r], {stdin.w: data})
                stdin.w = None # was closed by _do_io

                (pid_, exit_code, usage_) = os.wait4(pid, 0)

                self.contents = read[contents.r]
                self.status   = read[status.r]
                self.stderr   = read[stderr.r]

                if self.status == "":
                    raise GpgException("No status output from GPG. (GPG exited with status code %s)\n%s" % (exit_code, self.stderr))

                for line in self.status.splitlines():
                    self._parse_status(line)

                if require_signature and not self.valid:
                    raise GpgException("No valid signature found. (GPG exited with status code %s)\n%s" % (exit_code, self.stderr))

    def _do_io(self, read, write):
        for fd in write.keys():
            old = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, old | os.O_NONBLOCK)

        read_lines = dict( (fd, []) for fd in read )
        write_pos = dict( (fd, 0) for fd in write )

        read_set = list(read)
        write_set = write.keys()
        while len(read_set) > 0 or len(write_set) > 0:
            r, w, x_ = select.select(read_set, write_set, ())
            for fd in r:
                data = os.read(fd, 4096)
                if data == "":
                    read_set.remove(fd)
                read_lines[fd].append(data)
            for fd in w:
                data = write[fd][write_pos[fd]:]
                if data == "":
                    os.close(fd)
                    write_set.remove(fd)
                else:
                    bytes_written = os.write(fd, data)
                    write_pos[fd] += bytes_written

        return dict( (fd, "".join(read_lines[fd])) for fd in read_lines.keys() )

    def _parse_date(self, value):
        """parse date string in YYYY-MM-DD format

        @rtype:   L{datetime.datetime}
        @returns: datetime objects for 0:00 on the given day
        """
        year, month, day = value.split('-')
        date = datetime.date(int(year), int(month), int(day))
        time = datetime.time(0, 0)
        return datetime.datetime.combine(date, time)

    def _parse_status(self, line):
        fields = line.split()
        if fields[0] != "[GNUPG:]":
            raise GpgException("Unexpected output on status-fd: %s" % line)

        # VALIDSIG    <fingerprint in hex> <sig_creation_date> <sig-timestamp>
        #             <expire-timestamp> <sig-version> <reserved> <pubkey-algo>
        #             <hash-algo> <sig-class> <primary-key-fpr>
        if fields[1] == "VALIDSIG":
            self.valid = True
            self.fingerprint = fields[2]
            self.primary_fingerprint = fields[11]
            self.signature_timestamp = self._parse_date(fields[3])

        if fields[1] == "BADARMOR":
            raise GpgException("Bad armor.")

        if fields[1] == "NODATA":
            raise GpgException("No data.")

        if fields[1] == "DECRYPTION_FAILED":
            raise GpgException("Decryption failed.")

        if fields[1] == "ERROR":
            raise GpgException("Other error: %s %s" % (fields[2], fields[3]))

    def _exec_gpg(self, stdin, stdout, stderr, statusfd):
        try:
            if stdin != 0:
                os.dup2(stdin, 0)
            if stdout != 1:
                os.dup2(stdout, 1)
            if stderr != 2:
                os.dup2(stderr, 2)
            if statusfd != 3:
                os.dup2(statusfd, 3)
            for fd in range(4):
                old = fcntl.fcntl(fd, fcntl.F_GETFD)
                fcntl.fcntl(fd, fcntl.F_SETFD, old & ~fcntl.FD_CLOEXEC)
            os.closerange(4, _MAXFD)

            args = [self.gpg, "--status-fd=3", "--no-default-keyring"]
            for k in self.keyrings:
                args.append("--keyring=%s" % k)
            args.extend(["--decrypt", "-"])

            os.execvp(self.gpg, args)
        finally:
            os._exit(1)

    def contents_sha1(self):
        return apt_pkg.sha1sum(self.contents)

# vim: set sw=4 et:
