import sys

import apt_pkg


HASH_FIELDS = [
    ('SHA1-History', 0, 1),
    ('SHA256-History', 0, 2),
    ('SHA1-Patches', 1, 1),
    ('SHA256-Patches', 1, 2),
    ('SHA1-Download', 2, 1),
    ('SHA256-Download', 2, 2),
]

HASH_FIELDS_TABLE = {x[0]: (x[1], x[2]) for x in HASH_FIELDS}


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
                            self.filesizehashes = (int(l[1]), None, None)
                        self.filesizehashes = (int(self.filesizehashes[0]), l[0], self.filesizehashes[2])

                    if field == "SHA256-Current" and len(l) == 2:
                        if not self.filesizehashes:
                            self.filesizehashes = (int(l[1]), None, None)
                        self.filesizehashes = (int(self.filesizehashes[0]), self.filesizehashes[2], l[0])
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
                self.history[fname][ind] = (int(l[1]), None, None)
            if hashind == 1:
                self.history[fname][ind] = (int(self.history[fname][ind][0]), l[0], self.history[fname][ind][2])
            else:
                self.history[fname][ind] = (int(self.history[fname][ind][0]), self.history[fname][ind][1], l[0])

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
            if self.filesizehashes[1]:
                out.write("SHA1-Current: %s %7d\n" % (self.filesizehashes[1], self.filesizehashes[0]))
            if self.filesizehashes[2]:
                out.write("SHA256-Current: %s %7d\n" % (self.filesizehashes[2], self.filesizehashes[0]))

        hs = self.history
        order = self.history_order

        for fieldname, ind, hashind in HASH_FIELDS:
            out.write("%s:\n" % fieldname)
            for h in order:
                if hs[h][ind] and hs[h][ind][hashind]:
                    out.write(" %s %7d %s\n" % (hs[h][ind][hashind], hs[h][ind][0], h))

