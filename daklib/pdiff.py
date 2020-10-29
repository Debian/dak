import asyncio
import collections
import os
import subprocess
import sys
import tempfile

import apt_pkg

from daklib.dakapt import DakHashes

HASH_FIELDS = [
    ('SHA1-History', 0, 1, "", True),
    ('SHA256-History', 0, 2, "", True),
    ('SHA1-Patches', 1, 1, "", True),
    ('SHA256-Patches', 1, 2, "", True),
    ('SHA1-Download', 2, 1, ".gz", True),
    ('SHA256-Download', 2, 2, ".gz", True),
    ('X-Unmerged-SHA1-History', 0, 1, "", False),
    ('X-Unmerged-SHA256-History', 0, 2, "", False),
    ('X-Unmerged-SHA1-Patches', 1, 1, "", False),
    ('X-Unmerged-SHA256-Patches', 1, 2, "", False),
    ('X-Unmerged-SHA1-Download', 2, 1, ".gz", False),
    ('X-Unmerged-SHA256-Download', 2, 2, ".gz", False),
]

HASH_FIELDS_TABLE = {x[0]: (x[1], x[2], x[4]) for x in HASH_FIELDS}

_PDiffHashes = collections.namedtuple('_PDiffHashes', ['size', 'sha1', 'sha256'])


async def asyncio_check_call(*args, **kwargs):
    """async variant of subprocess.check_call

    Parameters reflect that of asyncio.create_subprocess_exec or
    (if "shell=True") that of asyncio.create_subprocess_shell
    with restore_signals=True being the default.
    """
    kwargs.setdefault('restore_signals', True)
    shell = kwargs.pop('shell', False)
    if shell:
        proc = await asyncio.create_subprocess_shell(*args, **kwargs)
    else:
        proc = await asyncio.create_subprocess_exec(*args, **kwargs)
    retcode = await proc.wait()
    if retcode != 0:
        raise subprocess.CalledProcessError(retcode, args[0])
    return 0


async def open_decompressed(file, named_temp_file=False):
    async def call_decompressor(cmd, inpath):
        fh = tempfile.NamedTemporaryFile("w+") if named_temp_file \
            else tempfile.TemporaryFile("w+")
        with open(inpath, "rb") as rfd:
            await asyncio_check_call(
                *cmd,
                stdin=rfd,
                stdout=fh,
            )
        fh.seek(0)
        return fh

    if os.path.isfile(file):
        return open(file, "r")
    elif os.path.isfile("%s.gz" % file):
        return await call_decompressor(['zcat'], '{}.gz'.format(file))
    elif os.path.isfile("%s.bz2" % file):
        return await call_decompressor(['bzcat'], '{}.bz2'.format(file))
    elif os.path.isfile("%s.xz" % file):
        return await call_decompressor(['xzcat'], '{}.xz'.format(file))
    else:
        return None


async def _merge_pdiffs(patch_a, patch_b, resulting_patch_without_extension):
    """Merge two pdiff in to a merged pdiff

    While rred support merging more than 2, we only need support for merging two.
    In the steady state, we will have N merged patches plus 1 new patch.  Here
    we need to do N pairwise merges (i.e. merge two patches N times).
    Therefore, supporting merging of 3+ patches does not help at all.

    The setup state looks like it could do with a bulk merging. However, if you
    merge from "latest to earliest" then you will be building in optimal order
    and still only need to do N-1 pairwise merges (rather than N-1 merges
    between N, N-1, N-2, ... 3, 2 patches).

    Combined, supporting pairwise merges is sufficient for our use case.
    """
    with await open_decompressed(patch_a, named_temp_file=True) as fd_a, \
            await open_decompressed(patch_b, named_temp_file=True) as fd_b:
        await asyncio_check_call(
            '/usr/lib/apt/methods/rred %s %s | gzip -9n > %s' % (fd_a.name, fd_b.name,
                                                                 resulting_patch_without_extension + ".gz"),
            shell=True,
        )


class PDiffHashes(_PDiffHashes):

    @classmethod
    def from_file(cls, fd):
        size = os.fstat(fd.fileno())[6]
        hashes = DakHashes(fd)
        return cls(size, hashes.sha1, hashes.sha256)


async def _pdiff_hashes_from_patch(path_without_extension):
    with await open_decompressed(path_without_extension) as difff:
        hashes_decompressed = PDiffHashes.from_file(difff)

    with open(path_without_extension + ".gz", "r") as difffgz:
        hashes_compressed = PDiffHashes.from_file(difffgz)

    return hashes_decompressed, hashes_compressed


def _prune_history(order, history, maximum):
    cnt = len(order)
    if cnt <= maximum:
        return order
    for h in order[:cnt - maximum]:
        del history[h]
    return order[cnt - maximum:]


def _read_hashes(history, history_order, ind, hashind, lines):
    current_order = []
    for line in lines:
        parts = line.split()
        fname = parts[2]
        if fname.endswith('.gz'):
            fname = fname[:-3]
        current_order.append(fname)
        if fname not in history:
            history[fname] = [None, None, None]
        if not history[fname][ind]:
            history[fname][ind] = PDiffHashes(int(parts[1]), None, None)
        if hashind == 1:
            history[fname][ind] = PDiffHashes(history[fname][ind].size,
                                              parts[0],
                                              history[fname][ind].sha256,
                                              )
        else:
            history[fname][ind] = PDiffHashes(history[fname][ind].size,
                                              history[fname][ind].sha1,
                                              parts[0],
                                              )

    # Common-case: Either this is the first sequence we read and we
    # simply adopt that
    if not history_order:
        return current_order
    # Common-case: The current history perfectly matches the existing, so
    # we just stop here.
    if current_order == history_order:
        return history_order

    # Special-case, the histories are not aligned.  This "should not happen"
    # but has done so in the past due to bugs.  Depending on which field is
    # out of sync, dak would either self heal or be stuff forever.  We
    # realign the history to ensure we always end with "self-heal".
    #
    # Typically, the patches are aligned from the end as we always add a
    # patch in the end of the series.
    patches_from_the_end = 0
    for p1, p2 in zip(reversed(current_order), reversed(history_order)):
        if p1 == p2:
            patches_from_the_end += 1
        else:
            break

    if not patches_from_the_end:
        return None

    return current_order[-patches_from_the_end:]


class PDiffIndex(object):
    def __init__(self, patches_dir, max=56, merge_pdiffs=False):
        self.can_path = None
        self._history = {}
        self._history_order = []
        self._unmerged_history = {}
        self._unmerged_history_order = []
        self._old_merged_patches_prefix = []
        self.max = max
        self.patches_dir = patches_dir
        self.filesizehashes = None
        self.wants_merged_pdiffs = merge_pdiffs
        self.has_merged_pdiffs = False
        self.index_path = os.path.join(patches_dir, 'Index')
        self.read_index_file(self.index_path)

    async def generate_and_add_patch_file(self, original_file, new_file_uncompressed, patch_name):

        with await open_decompressed(original_file) as oldf:
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
                await asyncio_check_call(
                    "diff --ed - {} | gzip --rsyncable  --no-name -c -9".format(new_file_uncompressed),
                    shell=True,
                    stdin=oldf,
                    stdout=fh
                )

            difsizehashes, difgzsizehashes = await _pdiff_hashes_from_patch(patch_path)

        self.filesizehashes = newsizehashes
        self._unmerged_history[patch_name] = [oldsizehashes,
                                              difsizehashes,
                                              difgzsizehashes,
                                              ]
        self._unmerged_history_order.append(patch_name)

        if self.has_merged_pdiffs != self.wants_merged_pdiffs:
            # Convert patches
            if self.wants_merged_pdiffs:
                await self._convert_to_merged_patches()
            else:
                self._convert_to_unmerged()
            # Conversion also covers the newly added patch.  Accordingly,
            # the elif here.
        else:
            second_patch_name = patch_name
            if self.wants_merged_pdiffs:
                await self._bump_merged_patches()
                second_patch_name = "T-%s-F-%s" % (patch_name, patch_name)
                os.link(os.path.join(self.patches_dir, patch_name + ".gz"),
                        os.path.join(self.patches_dir, second_patch_name + ".gz"))

            # Without merged PDiffs, keep _history and _unmerged_history aligned
            self._history[second_patch_name] = [oldsizehashes,
                                                difsizehashes,
                                                difgzsizehashes,
                                                ]
            self._history_order.append(second_patch_name)

    async def _bump_merged_patches(self):
        # When bumping patches, we need to "rewrite" all merged patches.  As
        # neither apt nor dak supports by-hash for pdiffs, we leave the old
        # versions of merged pdiffs behind.
        target_name = self._unmerged_history_order[-1]
        target_path = os.path.join(self.patches_dir, target_name)

        new_merged_order = []
        new_merged_history = {}
        for old_merged_patch_name in self._history_order:
            try:
                old_orig_name = old_merged_patch_name.split("-F-", 1)[1]
            except IndexError:
                old_orig_name = old_merged_patch_name
            new_merged_patch_name = "T-%s-F-%s" % (target_name, old_orig_name)
            old_merged_patch_path = os.path.join(self.patches_dir, old_merged_patch_name)
            new_merged_patch_path = os.path.join(self.patches_dir, new_merged_patch_name)
            await _merge_pdiffs(old_merged_patch_path, target_path, new_merged_patch_path)

            hashes_decompressed, hashes_compressed = await _pdiff_hashes_from_patch(new_merged_patch_path)

            new_merged_history[new_merged_patch_name] = [self._history[old_merged_patch_name][0],
                                                         hashes_decompressed,
                                                         hashes_compressed,
                                                         ]
            new_merged_order.append(new_merged_patch_name)

        self._history_order = new_merged_order
        self._history = new_merged_history

        self._old_merged_patches_prefix.append(self._unmerged_history_order[-1])

    def _convert_to_unmerged(self):
        if not self.has_merged_pdiffs:
            return
        # Converting from merged patches to unmerged patches is simply.  Discard the merged
        # patches.  Cleanup will be handled by find_obsolete_patches
        self._history = {k: v for k, v in self._unmerged_history.items()}
        self._history_order = list(self._unmerged_history_order)
        self._old_merged_patches_prefix = []
        self.has_merged_pdiffs = False

    async def _convert_to_merged_patches(self):
        if self.has_merged_pdiffs:
            return

        target_name = self._unmerged_history_order[-1]

        self._history = {}
        self._history_order = []

        new_patches = []

        # We merge from newest to oldest
        #
        # Assume we got N unmerged patches (u1 - uN) where given s1 then
        # you can apply u1 to get to s2. From s2 you use u2 to move to s3
        # and so on until you reach your target T (= sN+1).
        #
        # In the merged patch world, we want N merged patches called m1-N,
        # m2-N, m3-N ... m(N-1)-N.  Here, the you use sX + mX-N to go to
        # T directly regardless of where you start.
        #
        # A note worthy special case is that m(N-1)-N is identical uN
        # content-wise.  This will be important in a moment.  For now,
        # lets start with looking at creating merged patches.
        #
        # We can get m1-N by merging u1 with m2-N because u1 will take s1
        # to s2 and m2-N will take s2 to T.  By the same argument, we get
        # generate m2-N by combing u2 with m3-N.  Rinse-and-repeat until
        # we get to the base-case m(N-1)-N - which is uN.
        #
        # From this, we can conclude that generating the patches in
        # reverse order (i.e. m2-N is generated before m1-N) will get
        # us the desired result in N-1 pair-wise merges without having
        # to use all patches in one go.  (This is also optimal in the
        # sense that we need to update N-1 patches to preserve the
        # entire history).
        #
        for patch_name in reversed(self._unmerged_history_order):
            merged_patch = "T-%s-F-%s" % (target_name, patch_name)
            merged_patch_path = os.path.join(self.patches_dir, merged_patch)

            if new_patches:
                oldest_patch = os.path.join(self.patches_dir, patch_name)
                previous_merged_patch = os.path.join(self.patches_dir, new_patches[-1])
                await _merge_pdiffs(oldest_patch, previous_merged_patch, merged_patch_path)

                hashes_decompressed, hashes_compressed = await _pdiff_hashes_from_patch(merged_patch_path)

                self._history[merged_patch] = [self._unmerged_history[patch_name][0],
                                               hashes_decompressed,
                                               hashes_compressed,
                                               ]
            else:
                # Special_case; the latest patch is its own "merged" variant.
                os.link(os.path.join(self.patches_dir, patch_name + ".gz"), merged_patch_path + ".gz")
                self._history[merged_patch] = self._unmerged_history[patch_name]

            new_patches.append(merged_patch)

        self._history_order = list(reversed(new_patches))
        self._old_merged_patches_prefix.append(target_name)
        self.has_merged_pdiffs = True

    def read_index_file(self, index_file_path):
        try:
            with apt_pkg.TagFile(index_file_path) as index:
                index.step()
                section = index.section
                self.has_merged_pdiffs = section.get('X-Patch-Precedence') == 'merged'
                self._old_merged_patches_prefix = section.get('X-DAK-Older-Patches', '').split()

                for field in section.keys():
                    value = section[field]
                    if field in HASH_FIELDS_TABLE:
                        ind, hashind, primary_history = HASH_FIELDS_TABLE[field]
                        if primary_history:
                            history = self._history
                            history_order = self._history_order
                        else:
                            history = self._unmerged_history
                            history_order = self._unmerged_history_order

                        if history_order is None:
                            # History is already misaligned and we cannot find a common restore point.
                            continue

                        new_order = _read_hashes(history, history_order, ind, hashind, value.splitlines())
                        if primary_history:
                            self._history_order = new_order
                        else:
                            self._unmerged_history_order = new_order
                        continue

                    if field in ("Canonical-Name", "Canonical-Path"):
                        self.can_path = value
                        continue

                    if field not in ("SHA1-Current", "SHA256-Current"):
                        continue

                    l = value.split()

                    if len(l) != 2:
                        continue

                    if not self.filesizehashes:
                        self.filesizehashes = PDiffHashes(int(l[1]), None, None)

                    if field == "SHA1-Current":
                        self.filesizehashes = PDiffHashes(self.filesizehashes.size, l[0], self.filesizehashes.sha256)

                    if field == "SHA256-Current":
                        self.filesizehashes = PDiffHashes(self.filesizehashes.size, self.filesizehashes.sha1, l[0])

            # Ensure that the order lists are defined again.
            if self._history_order is None:
                self._history_order = []
            if self._unmerged_history_order is None:
                self._unmerged_history_order = []

            if not self.has_merged_pdiffs:
                # When X-Patch-Precedence != merged, then the two histories are the same.
                self._unmerged_history = {k: v for k, v in self._history.items()}
                self._unmerged_history_order = list(self._history_order)
                self._old_merged_patches_prefix = []

        except (IOError, apt_pkg.Error):
            # On error, we ignore everything.  This causes the file to be regenerated from scratch.
            # It forces everyone to download the full file for if they are behind.
            # But it is self-healing providing that we generate valid files from here on.
            pass

    def prune_patch_history(self):
        # Truncate our history if necessary
        hs = self._history
        order = self._history_order
        unmerged_hs = self._unmerged_history
        unmerged_order = self._unmerged_history_order
        self._history_order = _prune_history(order, hs, self.max)
        self._unmerged_history_order = _prune_history(unmerged_order, unmerged_hs, self.max)

        prefix_cnt = len(self._old_merged_patches_prefix)
        if prefix_cnt > 3:
            self._old_merged_patches_prefix = self._old_merged_patches_prefix[prefix_cnt - 3:]

    def find_obsolete_patches(self):
        if not os.path.isdir(self.patches_dir):
            return

        hs = self._history
        unmerged_hs = self._unmerged_history

        keep_prefixes = tuple("T-%s-F-" % x for x in self._old_merged_patches_prefix)

        # Scan for obsolete patches.  While we could have computed these
        # from the history, this method has the advantage of cleaning up
        # old patches left that we failed to remove previously (e.g. if
        # we had an index corruption, which happened in fed7ada36b609 and
        # was later fixed in a36f867acf029)
        for name in os.listdir(self.patches_dir):
            if name in ('Index', 'by-hash'):
                continue
            # We keep some old merged patches around (as neither apt nor
            # dak supports by-hash for pdiffs)
            if keep_prefixes and name.startswith(keep_prefixes):
                continue
            basename, ext = os.path.splitext(name)
            if ext in ('', '.gz') and (basename in hs or basename in unmerged_hs):
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

        for fieldname, ind, hashind, ext, primary_history in HASH_FIELDS:

            if primary_history:
                hs = self._history
                order = self._history_order
            elif self.has_merged_pdiffs:
                hs = self._unmerged_history
                order = self._unmerged_history_order
            else:
                continue

            out.write("%s:\n" % fieldname)
            for h in order:
                if hs[h][ind] and hs[h][ind][hashind]:
                    out.write(" %s %7d %s%s\n" % (hs[h][ind][hashind], hs[h][ind].size, h, ext))

        if self.has_merged_pdiffs:
            out.write("X-Patch-Precedence: merged\n")
            if self._old_merged_patches_prefix:
                out.write("X-DAK-Older-Patches: %s\n" % " ".join(self._old_merged_patches_prefix))

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
