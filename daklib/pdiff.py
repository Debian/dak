import collections
import os
import sys

import apt_pkg

from daklib.dakapt import DakHashes

HASH_FIELDS = [
    ('SHA1-History', 0, 1),
    ('SHA256-History', 0, 2),
    ('SHA1-Patches', 1, 1),
    ('SHA256-Patches', 1, 2),
    ('SHA1-Download', 2, 1),
    ('SHA256-Download', 2, 2),
]

HASH_FIELDS_TABLE = {x[0]: (x[1], x[2]) for x in HASH_FIELDS}

_PDiffHashes = collections.namedtuple('_PDiffHashes', ['size', 'sha1', 'sha256'])


class PDiffHashes(_PDiffHashes):

    @classmethod
    def from_file(cls, fd):
        size = os.fstat(fd.fileno())[6]
        hashes = DakHashes(fd)
        return cls(size, hashes.sha1, hashes.sha256)


class PDiffIndex(object):
    def __init__(self, readpath=None, max=56):
        self.can_path = None
        self.history = {}
        self.history_order = []
        self.max = max
        self.readpath = readpath
        self.filesizehashes = None

        if readpath:
            self.read_index_file(readpath + "/Index")

    def add_patch_file(self, patch_name, base_file_hashes, target_file_hashes,
                       patch_hashes_uncompressed, patch_hashes_compressed,
                       ):
        self.history[patch_name] = [base_file_hashes,
                                    patch_hashes_uncompressed,
                                    patch_hashes_compressed,
                                    ]
        self.history_order.append(patch_name)
        self.filesizehashes = target_file_hashes

    def read_index_file(self, index_file_path):
        try:
            with apt_pkg.TagFile(index_file_path) as index:
                index.step()
                section = index.section

                for field in section.keys():
                    value = section[field]
                    if field in HASH_FIELDS_TABLE:
                        ind, hashind = HASH_FIELDS_TABLE[field]
                        self.read_hashes(ind, hashind, value.splitlines())
                        continue

                    if field in ("Canonical-Name", "Canonical-Path"):
                        self.can_path = value
                        continue

                    if field not in ("SHA1-Current", "SHA256-Current"):
                        continue

                    l = value.split()

                    if field == "SHA1-Current" and len(l) == 2:
                        if not self.filesizehashes:
                            self.filesizehashes = PDiffHashes(int(l[1]), None, None)
                        self.filesizehashes = PDiffHashes(self.filesizehashes.size, l[0], self.filesizehashes.sha256)

                    if field == "SHA256-Current" and len(l) == 2:
                        if not self.filesizehashes:
                            self.filesizehashes = PDiffHashes(int(l[1]), None, None)
                        self.filesizehashes = PDiffHashes(self.filesizehashes.size, self.filesizehashes.sha1, l[0])

        except (IOError, apt_pkg.Error):
            # On error, we ignore everything.  This causes the file to be regenerated from scratch.
            # It forces everyone to download the full file for if they are behind.
            # But it is self-healing providing that we generate valid files from here on.
            pass

    def read_hashes(self, ind, hashind, lines):
        for line in lines:
            l = line.split()
            fname = l[2]
            if fname.endswith('.gz'):
                fname = fname[:-3]
            if fname not in self.history:
                self.history[fname] = [None, None, None]
                self.history_order.append(fname)
            if not self.history[fname][ind]:
                self.history[fname][ind] = PDiffHashes(int(l[1]), None, None)
            if hashind == 1:
                self.history[fname][ind] = PDiffHashes(self.history[fname][ind].size,
                                                       l[0],
                                                       self.history[fname][ind].sha256,
                                                       )
            else:
                self.history[fname][ind] = PDiffHashes(self.history[fname][ind].size,
                                                       self.history[fname][ind].sha1,
                                                       l[0],
                                                       )

    def prune_obsolete_pdiffs(self):
        hs = self.history
        order = self.history_order[:]

        cnt = len(order)
        if cnt > self.max:
            for h in order[:cnt - self.max]:
                yield "%s/%s.gz" % (self.readpath, h)
                del hs[h]
            order = order[cnt - self.max:]
            self.history_order = order

    def dump(self, out=sys.stdout):
        if self.can_path:
            out.write("Canonical-Path: %s\n" % self.can_path)

        if self.filesizehashes:
            if self.filesizehashes.sha1:
                out.write("SHA1-Current: %s %7d\n" % (self.filesizehashes.sha1, self.filesizehashes.size))
            if self.filesizehashes.sha256:
                out.write("SHA256-Current: %s %7d\n" % (self.filesizehashes.sha256, self.filesizehashes.size))

        hs = self.history
        order = self.history_order

        for fieldname, ind, hashind in HASH_FIELDS:
            out.write("%s:\n" % fieldname)
            for h in order:
                if hs[h][ind] and hs[h][ind][hashind]:
                    out.write(" %s %7d %s\n" % (hs[h][ind][hashind], hs[h][ind].size, h))

