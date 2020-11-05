import collections
import os
import sys
import tempfile

import apt_pkg

from daklib import daksubprocess
from daklib.dakapt import DakHashes

HASH_FIELDS = [
    ('SHA1-History', 0, 1, ""),
    ('SHA256-History', 0, 2, ""),
    ('SHA1-Patches', 1, 1, ""),
    ('SHA256-Patches', 1, 2, ""),
    ('SHA1-Download', 2, 1, ".gz"),
    ('SHA256-Download', 2, 2, ".gz"),
]

HASH_FIELDS_TABLE = {x[0]: (x[1], x[2]) for x in HASH_FIELDS}

_PDiffHashes = collections.namedtuple('_PDiffHashes', ['size', 'sha1', 'sha256'])


def open_decompressed(path):
    def call_decompressor(cmd, inpath):
        fh = tempfile.TemporaryFile("w+")
        with open(inpath) as rfh:
            daksubprocess.check_call(
                cmd,
                stdin=rfh,
                stdout=fh,
            )
        fh.seek(0)
        return fh

    if os.path.isfile(path):
        return open(path, "r")
    elif os.path.isfile("%s.gz" % path):
        return call_decompressor(['zcat'], '{}.gz'.format(path))
    elif os.path.isfile("%s.bz2" % path):
        return call_decompressor(['bzcat'], '{}.bz2'.format(path))
    elif os.path.isfile("%s.xz" % path):
        return call_decompressor(['xzcat'], '{}.xz'.format(path))
    else:
        return None


class PDiffHashes(_PDiffHashes):

    @classmethod
    def from_file(cls, fd):
        size = os.fstat(fd.fileno())[6]
        hashes = DakHashes(fd)
        return cls(size, hashes.sha1, hashes.sha256)


class PDiffIndex(object):
    def __init__(self, patches_dir, max=56):
        self.can_path = None
        self.history = {}
        self.history_order = []
        self.max = max
        self.patches_dir = patches_dir
        self.filesizehashes = None
        self.index_path = os.path.join(patches_dir, 'Index')
        self.read_index_file(self.index_path)

    def add_patch_file(self, patch_name, base_file_hashes, target_file_hashes,
                       patch_hashes_uncompressed, patch_hashes_compressed,
                       ):
        self.history[patch_name] = [base_file_hashes,
                                    patch_hashes_uncompressed,
                                    patch_hashes_compressed,
                                    ]
        self.history_order.append(patch_name)
        self.filesizehashes = target_file_hashes

    def generate_and_add_patch_file(self, original_file, new_file_uncompressed, patch_name):

        with open_decompressed(original_file) as oldf:
            oldsizehashes = PDiffHashes.from_file(oldf)

            with open(new_file_uncompressed, "r") as newf:
                newsizehashes = PDiffHashes.from_file(newf)

            if newsizehashes == oldsizehashes:
                return

            if not os.path.isdir(self.patches_dir):
                os.mkdir(self.patches_dir)

            oldf.seek(0)
            patch_path = os.path.join(self.patches_dir, patch_name)
            with open("{}.gz".format(patch_path), "wb") as fh:
                daksubprocess.check_call(
                    "diff --ed - {} | gzip --rsyncable  --no-name -c -9".format(new_file_uncompressed),
                    shell=True,
                    stdin=oldf,
                    stdout=fh
                )

        with open_decompressed(patch_path) as difff:
            difsizehashes = PDiffHashes.from_file(difff)

        with open(patch_path + ".gz", "r") as difffgz:
            difgzsizehashes = PDiffHashes.from_file(difffgz)

        self.add_patch_file(patch_name, oldsizehashes, newsizehashes, difsizehashes, difgzsizehashes)

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

    def prune_patch_history(self):
        hs = self.history
        order = self.history_order[:]

        # Truncate our history if necessary
        cnt = len(order)
        if cnt > self.max:
            for h in order[:cnt - self.max]:
                del hs[h]
            order = order[cnt - self.max:]
            self.history_order = order

    def find_obsolete_patches(self):
        if not os.path.isdir(self.patches_dir):
            return

        hs = self.history
        # Scan for obsolete patches.  While we could have computed these
        # from the history, this method has the advantage of cleaning up
        # old patches left that we failed to remove previously (e.g. if
        # we had an index corruption, which happened in fed7ada36b609 and
        # was later fixed in a36f867acf029)
        for name in os.listdir(self.patches_dir):
            if name in ('Index', 'by-hash'):
                continue
            basename, ext = os.path.splitext(name)
            if basename in hs and ext in ('', '.gz'):
                continue
            path = os.path.join(self.patches_dir, name)
            if not os.path.isfile(path):
                # Non-files are probably not patches.
                continue
            # Unknown patch file; flag it as obsolete
            yield path

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

        for fieldname, ind, hashind, ext in HASH_FIELDS:
            out.write("%s:\n" % fieldname)
            for h in order:
                if hs[h][ind] and hs[h][ind][hashind]:
                    out.write(" %s %7d %s%s\n" % (hs[h][ind][hashind], hs[h][ind].size, h, ext))

    def update_index(self, tmp_suffix=".new"):
        if not os.path.isdir(self.patches_dir):
            # If there is no patch directory, then we have no patches.
            # It seems weird to have an Index of patches when we know there are
            # none.
            return
        tmp_path = self.index_path + tmp_suffix
        with open(tmp_path, "w") as f:
            self.dump(f)
        os.rename(tmp_path, self.index_path)
