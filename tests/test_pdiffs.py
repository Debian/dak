import contextlib
import os
import shutil
import tempfile
import unittest

from daklib.pdiff import PDiffIndex

try:
    from unittest import IsolatedAsyncioTestCase
except ImportError:
    IsolatedAsyncioTestCase = None


def generate_orig(content_dir, initial_content):
    current_file = os.path.join(content_dir, "data-current")
    with open(current_file, 'wt') as fd:
        if isinstance(initial_content, list):
            fd.writelines("{}\n".format(line) for line in initial_content)
        else:
            fd.write(initial_content)


async def generate_patch(index, patch_name, content_dir, new_content):
    new_file = os.path.join(content_dir, "data-current")
    orig_file = os.path.join(content_dir, "data-previous")

    if os.path.isfile(new_file):
        os.rename(new_file, orig_file)
    elif not os.path.isfile(orig_file):
        # Ensure there is an empty orig file
        with open(orig_file, 'w'):
            pass

    generate_orig(content_dir, new_content)

    await index.generate_and_add_patch_file(orig_file, new_file, patch_name)


def prune_history(index, known_patch_count_before=None, known_patch_count_after=None, detected_obsolete_patches=None):

    if known_patch_count_before is not None:
        assert len(index._history) == known_patch_count_before
    index.prune_patch_history()
    if known_patch_count_after is not None:
        assert len(index._history) == known_patch_count_after
    if detected_obsolete_patches is not None:
        assert sorted(os.path.basename(p) for p in index.find_obsolete_patches()) == detected_obsolete_patches


def delete_obsolete_patches(index):
    for patch_file in index.find_obsolete_patches():
        os.unlink(patch_file)


def reload_and_compare_pdiff_indices(index):
    reloaded_index = PDiffIndex(index.patches_dir, index.max, index.wants_merged_pdiffs)
    assert index._history_order == reloaded_index._history_order
    assert index._history == reloaded_index._history
    assert index._old_merged_patches_prefix == reloaded_index._old_merged_patches_prefix
    assert index._unmerged_history_order == reloaded_index._unmerged_history_order
    # Only part of the history is carried over. Ignore the missing bits.
    assert [index._history[x][0] for x in index._history_order] == \
           [reloaded_index._history[x][0] for x in reloaded_index._history_order]
    assert [index._history[x][2].size for x in index._history_order] == \
           [reloaded_index._history[x][2].size for x in reloaded_index._history_order]
    assert [index._history[x][2].sha256 for x in index._history_order] == \
           [reloaded_index._history[x][2].sha256 for x in reloaded_index._history_order]

    if index.wants_merged_pdiffs:
        assert [index._unmerged_history[x][0] for x in index._unmerged_history_order] == \
               [reloaded_index._unmerged_history[x][0] for x in reloaded_index._unmerged_history_order]
        assert [index._unmerged_history[x][2].size for x in index._unmerged_history_order] == \
               [reloaded_index._unmerged_history[x][2].size for x in reloaded_index._unmerged_history_order]
        assert [index._unmerged_history[x][2].sha256 for x in index._unmerged_history_order] == \
               [reloaded_index._unmerged_history[x][2].sha256 for x in reloaded_index._unmerged_history_order]
        assert len(index._history_order) == len(reloaded_index._unmerged_history_order)

        for unmerged_patch in index._unmerged_history_order:
            assert unmerged_patch.startswith('patch')

        for merged_patch in index._history_order:
            assert merged_patch.startswith('T-patch')

    assert index.filesizehashes == reloaded_index.filesizehashes
    assert index.can_path == reloaded_index.can_path
    assert index.has_merged_pdiffs == reloaded_index.has_merged_pdiffs

    return reloaded_index


@contextlib.contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


MISALIGNED_HISTORY_RESTORABLE = """
SHA1-Current: 2f846350bf5855230190ef1588e9ee5ddc45b7c7 13499355
SHA256-Current: 17f0429f6116d47a75ac05e5598cac50b9ba511386e849628ef3b6dad0247d17 13499355
SHA1-History:
 05e82a87ced6a0827d38bdcc84b0a795512d48e8 13992555 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 7f5c4a7946dd2fb52e51ef7103ab1ee26c210d3a 13985915 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 6d2356c893e6c37a1957f3ae751af7da389ba37e 13981903 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 1935ed98c30fa9eef8d4a22a70614e969a1ec7b0 13761106 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 e791a3eed4b51744d91d7fd3100adddab2439655 13565058 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA256-History:
 82d074d6437e4bf20d1e5e99641f2576c42257bde8acf6310cf2ea1d208c189b 13992555 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 beed2758c3f93c8f27d83de51e37f6686861648c2ceeae8efb0f1701340e279c 13985915 TOTALLY_WRONG
 668c0bb52edec49d27b0d0e673ae955798bfbe031edb779573903be9d20c1116 13981903 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 c7f2ff9bd51b42cb965f7cac2691ede8029422a14f6727ad255ebcc02b7db2f8 13761106 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 33ac90a88d12023ce762772c8422e65ad62528b1de8b579780729978fdf9f437 13565058 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA1-Patches:
 a1799e3fa0d47f6745a90b3e10e1eae442892f02 6093771 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 45a0e17714357501c0251fc2f30ac3dad98bad85 6093711 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 5d8ef7b8288024666148d89d2bb4a973bc41a682 6093597 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 9f4ff66bc61c67070af0b8925a8c1889eab47ebd 6093251 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 3a7650a9c9656872653a8c990ac802e547eff394     584 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA256-Patches:
 52cb3df2e78f012b7eb8ee4bad8bb2cdc185ce96dc1ff449222d49f454618b76 6093771 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 b8e607100e642b1e3127ac4751528d8fc9ffe413953a9afcedb0473cac135cd9 6093711 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 eabd2eaf70c6cfcb5108f1496bf971eee18b6848f9bca77bf3599c92a21993da 6093597 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 70b95b9c4dd14e34706cc9063094621b04cb187f9f29f7057dff90183b11b21b 6093251 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 26ceafe212bdfb45394ebbeb0d8980af01efdd6a07a78424d6cda268c797e344     584 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA1-Download:
 4ca7db18342fca28d2b9e59fec463776fd14931e  387469 GONE_WITH_THE_WIND
 3d8aeb4b658fab36ae43198102a113922ef6ad21  387406 T-2020-12-12-0800.11-F-2020-11-26-0822.42.gz
 11db8148e26030f65b7d29041f805b6534329f9a     271 T-2020-12-12-0800.11-F-2020-12-12-0800.11.gz
SHA256-Download:
 dbf9a732491fe685d209a3da8d03609b874079b6b50dd1db8990854817e168be  387492 T-2020-12-12-0800.11-F-2020-11-25-0812.03.gz
 3aea0a0443f624be3b3664e037634ff74b7f59631dad797d075464b8733f4cf4  387500 T-2020-12-12-0800.11-F-2020-11-25-2013.43.gz
 1b96280550272f576e22b1901b100e9b7062ae9b9957fe26088b516f73611ee3  387469 T-2020-12-12-0800.11-F-2020-11-26-0212.42.gz
 05ea55afd7e30cd9556d96ab211714fec51a6c71c486ca20514e9c04d091ef30  387406 T-2020-12-12-0800.11-F-2020-11-26-0822.42.gz
 acf2997c8ddc7e9e935154ee9807f8777d25c81fa3eb35c53ec0d94d8fb0f21d     271 T-2020-12-12-0800.11-F-2020-12-12-0800.11.gz
X-Unmerged-SHA1-History:
 e791a3eed4b51744d91d7fd3100adddab2439655 13565058 2020-12-12-0800.11
X-Unmerged-SHA256-History:
 33ac90a88d12023ce762772c8422e65ad62528b1de8b579780729978fdf9f437 13565058 2020-12-12-0800.11
X-Unmerged-SHA1-Patches:
 a4628688d21d3cfe21a560b614f9c0909b66c98f 7158486 T-2020-12-09-0202.31-F-2020-11-22-0214.58
 7c652dc66607ad7f568414fb0fe6386cbf8979f3 7103094 T-2020-12-09-0202.31-F-2020-11-22-0816.18
 29b8e86a32ea4493608b45efb7a7e453fb07bc64 7102980 T-2020-12-09-0202.31-F-2020-11-22-1420.12
 ab93e3c10d0d557dfb097b8ff0eb0b6b7029f700 7019210 T-2020-12-09-0202.31-F-2020-11-22-2016.07
 3a7650a9c9656872653a8c990ac802e547eff394     584 2020-12-12-0800.11
X-Unmerged-SHA256-Patches:
 3ac4c2cb60dce35ee059263ddf063379737a84b5dd7459d5b95471afa3b86a00 7158486 T-2020-12-09-0202.31-F-2020-11-22-0214.58
 47949559026c2253b18cc769cac858d5ccababf9236ac26ec75cb68c90d226cd 7103094 T-2020-12-09-0202.31-F-2020-11-22-0816.18
 f791e377a6b3cb80c9c2b6c0cdc88c59b337f0443bfb5c4116d17126dbb8ca14 7102980 T-2020-12-09-0202.31-F-2020-11-22-1420.12
 1a8045dabd177304ca32350d40cb16d1e0e1ec1998f69f20a139685c978fa263 7019210 T-2020-12-09-0202.31-F-2020-11-22-2016.07
 043e62ea9c798aab6f2cfe5fa50d091ed44048396f2130272bb25f08b11351ff 6963749 T-2020-12-09-0202.31-F-2020-11-23-0221.04
 26ceafe212bdfb45394ebbeb0d8980af01efdd6a07a78424d6cda268c797e344     584 2020-12-12-0800.11
X-Unmerged-SHA1-Download:
 11db8148e26030f65b7d29041f805b6534329f9a     271 2020-12-12-0800.11.gz
X-Unmerged-SHA256-Download:
 acf2997c8ddc7e9e935154ee9807f8777d25c81fa3eb35c53ec0d94d8fb0f21d     271 2020-12-12-0800.11.gz
X-Patch-Precedence: merged
X-DAK-Older-Patches: 2020-12-11-2002.18 2020-12-12-0200.49 2020-12-12-0800.11
"""

MISALIGNED_HISTORY_BROKEN = """
SHA1-Current: 2f846350bf5855230190ef1588e9ee5ddc45b7c7 13499355
SHA256-Current: 17f0429f6116d47a75ac05e5598cac50b9ba511386e849628ef3b6dad0247d17 13499355
SHA1-History:
 05e82a87ced6a0827d38bdcc84b0a795512d48e8 13992555 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 7f5c4a7946dd2fb52e51ef7103ab1ee26c210d3a 13985915 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 6d2356c893e6c37a1957f3ae751af7da389ba37e 13981903 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 1935ed98c30fa9eef8d4a22a70614e969a1ec7b0 13761106 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 e791a3eed4b51744d91d7fd3100adddab2439655 13565058 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA256-History:
 82d074d6437e4bf20d1e5e99641f2576c42257bde8acf6310cf2ea1d208c189b 13992555 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 beed2758c3f93c8f27d83de51e37f6686861648c2ceeae8efb0f1701340e279c 13985915 TOTALLY_WRONG
 668c0bb52edec49d27b0d0e673ae955798bfbe031edb779573903be9d20c1116 13981903 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 c7f2ff9bd51b42cb965f7cac2691ede8029422a14f6727ad255ebcc02b7db2f8 13761106 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 33ac90a88d12023ce762772c8422e65ad62528b1de8b579780729978fdf9f437 13565058 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA1-Patches:
 a1799e3fa0d47f6745a90b3e10e1eae442892f02 6093771 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 45a0e17714357501c0251fc2f30ac3dad98bad85 6093711 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 5d8ef7b8288024666148d89d2bb4a973bc41a682 6093597 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 9f4ff66bc61c67070af0b8925a8c1889eab47ebd 6093251 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 3a7650a9c9656872653a8c990ac802e547eff394     584 T-2020-12-12-0800.11-F-2020-12-12-0800.11
SHA256-Patches:
 52cb3df2e78f012b7eb8ee4bad8bb2cdc185ce96dc1ff449222d49f454618b76 6093771 T-2020-12-12-0800.11-F-2020-11-25-0812.03
 b8e607100e642b1e3127ac4751528d8fc9ffe413953a9afcedb0473cac135cd9 6093711 T-2020-12-12-0800.11-F-2020-11-25-2013.43
 eabd2eaf70c6cfcb5108f1496bf971eee18b6848f9bca77bf3599c92a21993da 6093597 T-2020-12-12-0800.11-F-2020-11-26-0212.42
 70b95b9c4dd14e34706cc9063094621b04cb187f9f29f7057dff90183b11b21b 6093251 T-2020-12-12-0800.11-F-2020-11-26-0822.42
 26ceafe212bdfb45394ebbeb0d8980af01efdd6a07a78424d6cda268c797e344     584 T_T
SHA1-Download:
 4ca7db18342fca28d2b9e59fec463776fd14931e  387469 GONE_WITH_THE_WIND
 3d8aeb4b658fab36ae43198102a113922ef6ad21  387406 T-2020-12-12-0800.11-F-2020-11-26-0822.42.gz
 11db8148e26030f65b7d29041f805b6534329f9a     271 T-2020-12-12-0800.11-F-2020-12-12-0800.11.gz
SHA256-Download:
 dbf9a732491fe685d209a3da8d03609b874079b6b50dd1db8990854817e168be  387492 T-2020-12-12-0800.11-F-2020-11-25-0812.03.gz
 3aea0a0443f624be3b3664e037634ff74b7f59631dad797d075464b8733f4cf4  387500 T-2020-12-12-0800.11-F-2020-11-25-2013.43.gz
 1b96280550272f576e22b1901b100e9b7062ae9b9957fe26088b516f73611ee3  387469 T-2020-12-12-0800.11-F-2020-11-26-0212.42.gz
 05ea55afd7e30cd9556d96ab211714fec51a6c71c486ca20514e9c04d091ef30  387406 O_O.gz
 acf2997c8ddc7e9e935154ee9807f8777d25c81fa3eb35c53ec0d94d8fb0f21d     271 T-2020-12-12-0800.11-F-2020-12-12-0800.11.gz
"""

if IsolatedAsyncioTestCase is not None:
    class TestPDiffs(IsolatedAsyncioTestCase):

        async def test_corrupt_pdiff_index(self):
            with tempdir() as tmpdir:
                pdiff_dir = os.path.join(tmpdir, "pdiffs")
                index_file = os.path.join(pdiff_dir, 'Index')
                os.mkdir(pdiff_dir)
                with open(index_file, 'w') as fd:
                    fd.write(MISALIGNED_HISTORY_RESTORABLE)

                index = PDiffIndex(pdiff_dir, 3, False)
                assert index._history_order == [
                    "T-2020-12-12-0800.11-F-2020-11-26-0822.42",
                    "T-2020-12-12-0800.11-F-2020-12-12-0800.11",
                ]
                assert index._unmerged_history_order == ["2020-12-12-0800.11"]

                with open(index_file, 'w') as fd:
                    fd.write(MISALIGNED_HISTORY_BROKEN)

                index = PDiffIndex(pdiff_dir, 3, False)
                assert index._history_order == []
                assert index._unmerged_history_order == []

        async def test_pdiff_index_unmerged(self):
            with tempdir() as tmpdir:
                pdiff_dir = os.path.join(tmpdir, "pdiffs")
                index_file = os.path.join(pdiff_dir, 'Index')
                index = PDiffIndex(pdiff_dir, 3, False)

                data = [
                    'Version 0',
                    'Some',
                    'data',
                    'across',
                    '6',
                    'lines',
                ]

                # The pdiff system assumes we start from a non-empty file
                generate_orig(tmpdir, data)
                data[0] = 'Version 1'

                # Non-existing directory => empty history
                prune_history(index,
                              known_patch_count_before=0,
                              known_patch_count_after=0,
                              detected_obsolete_patches=[]
                              )
                # Update should be possible but do nothing
                # (dak generate-index-diffs relies on this behaviour)
                index.update_index()
                # It should not create the directory
                assert not os.path.isdir(pdiff_dir)

                # Adding a patch should "just work(tm)"
                await generate_patch(index, "patch-1", tmpdir, data)
                assert os.path.isdir(pdiff_dir)
                assert index.filesizehashes is not None
                assert index.filesizehashes.size > 0
                prune_history(index,
                              known_patch_count_before=1,
                              known_patch_count_after=1,
                              detected_obsolete_patches=[]
                              )
                assert not os.path.isfile(index_file)
                index.update_index()
                assert os.path.isfile(index_file)

                reload_and_compare_pdiff_indices(index)

                index.can_path = "/some/where"

                # We should detect obsolete files that are not part of the
                # history.
                with open(os.path.join(pdiff_dir, "random-patch"), "w"):
                    pass

                prune_history(index,
                              known_patch_count_before=1,
                              known_patch_count_after=1,
                              detected_obsolete_patches=['random-patch']
                              )

                delete_obsolete_patches(index)

                data[0] = 'Version 2'
                data[3] = 'over'
                await generate_patch(index, "patch-2", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=2,
                              known_patch_count_after=2,
                              detected_obsolete_patches=[]
                              )

                data[2] = 'Text'

                await generate_patch(index, "patch-3", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=3,
                              known_patch_count_after=3,
                              detected_obsolete_patches=[]
                              )

                data[0] = 'Version 3'

                await generate_patch(index, "patch-4", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['patch-1.gz']
                              )

                data[0] = 'Version 4'
                data[-1] = 'lines.'

                await generate_patch(index, "patch-5", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['patch-1.gz', 'patch-2.gz']
                              )

                index.update_index()
                reload_and_compare_pdiff_indices(index)

                delete_obsolete_patches(index)

        async def test_pdiff_index_merged(self):
            with tempdir() as tmpdir:
                pdiff_dir = os.path.join(tmpdir, "pdiffs")
                index_file = os.path.join(pdiff_dir, 'Index')
                index = PDiffIndex(pdiff_dir, 3, True)

                data = [
                    'Version 0',
                    'Some',
                    'data',
                    'across',
                    '6',
                    'lines',
                ]

                # The pdiff system assumes we start from a non-empty file
                generate_orig(tmpdir, data)
                data[0] = 'Version 1'

                # Non-existing directory => empty history
                prune_history(index,
                              known_patch_count_before=0,
                              known_patch_count_after=0,
                              detected_obsolete_patches=[]
                              )
                # Update should be possible but do nothing
                # (dak generate-index-diffs relies on this behaviour)
                index.update_index()
                # It should not create the directory
                assert not os.path.isdir(pdiff_dir)

                # Adding a patch should "just work(tm)"
                await generate_patch(index, "patch-1", tmpdir, data)
                assert os.path.isdir(pdiff_dir)
                assert index.filesizehashes is not None
                assert index.filesizehashes.size > 0
                prune_history(index,
                              known_patch_count_before=1,
                              known_patch_count_after=1,
                              detected_obsolete_patches=[]
                              )
                assert not os.path.isfile(index_file)
                index.update_index()
                assert os.path.isfile(index_file)

                reload_and_compare_pdiff_indices(index)

                index.can_path = "/some/where"

                data[0] = 'Version 2'
                data[3] = 'over'
                await generate_patch(index, "patch-2", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=2,
                              known_patch_count_after=2,
                              detected_obsolete_patches=[]
                              )

                data[2] = 'Text'

                await generate_patch(index, "patch-3", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=3,
                              known_patch_count_after=3,
                              detected_obsolete_patches=[]
                              )

                data[0] = 'Version 3'

                await generate_patch(index, "patch-4", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['T-patch-1-F-patch-1.gz', 'patch-1.gz']
                              )

                data[0] = 'Version 4'
                data[-1] = 'lines.'

                await generate_patch(index, "patch-5", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['T-patch-1-F-patch-1.gz',

                                                         'T-patch-2-F-patch-1.gz',
                                                         'T-patch-2-F-patch-2.gz',

                                                         'patch-1.gz',
                                                         'patch-2.gz'
                                                         ]
                              )

                index.update_index()
                # Swap to the reloaded index.  Assuming everything works as intended
                # this should not matter.
                reload_and_compare_pdiff_indices(index)

                data[0] = 'Version 5'

                await generate_patch(index, "patch-6", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['T-patch-1-F-patch-1.gz',

                                                         'T-patch-2-F-patch-1.gz',
                                                         'T-patch-2-F-patch-2.gz',

                                                         'T-patch-3-F-patch-1.gz',
                                                         'T-patch-3-F-patch-2.gz',
                                                         'T-patch-3-F-patch-3.gz',

                                                         'patch-1.gz',
                                                         'patch-2.gz',
                                                         'patch-3.gz',
                                                         ]
                              )

                delete_obsolete_patches(index)

                data[0] = 'Version 6'

                await generate_patch(index, "patch-7", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=[
                                                         'T-patch-4-F-patch-1.gz',
                                                         'T-patch-4-F-patch-2.gz',
                                                         'T-patch-4-F-patch-3.gz',
                                                         'T-patch-4-F-patch-4.gz',

                                                         'patch-4.gz',
                                                         ]
                              )

                delete_obsolete_patches(index)
                index.update_index()
                reload_and_compare_pdiff_indices(index)

                # CHANGING TO NON-MERGED INDEX
                index = PDiffIndex(pdiff_dir, 3, False)

                data[0] = 'Version 7'

                # We need to add a patch to trigger the conversion
                await generate_patch(index, "patch-8", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=[
                                                         'T-patch-5-F-patch-2.gz',
                                                         'T-patch-5-F-patch-3.gz',
                                                         'T-patch-5-F-patch-4.gz',
                                                         'T-patch-5-F-patch-5.gz',

                                                         'T-patch-6-F-patch-3.gz',
                                                         'T-patch-6-F-patch-4.gz',
                                                         'T-patch-6-F-patch-5.gz',
                                                         'T-patch-6-F-patch-6.gz',

                                                         'T-patch-7-F-patch-4.gz',
                                                         'T-patch-7-F-patch-5.gz',
                                                         'T-patch-7-F-patch-6.gz',
                                                         'T-patch-7-F-patch-7.gz',

                                                         'patch-5.gz',
                                                         ]
                              )

                delete_obsolete_patches(index)
                index.update_index()

                # CHANGING BACK TO MERGED

                index = PDiffIndex(pdiff_dir, 3, True)

                data[0] = 'Version 8'

                # We need to add a patch to trigger the conversion
                await generate_patch(index, "patch-9", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=['patch-6.gz']
                              )

                delete_obsolete_patches(index)
                index.update_index()

                # CHANGING TO NON-MERGED INDEX (AGAIN)
                # This will trip the removal of all the merged patches, proving they
                # were generated in the first place.
                index = PDiffIndex(pdiff_dir, 3, False)

                data[0] = 'Version 9'

                # We need to add a patch to trigger the conversion
                await generate_patch(index, "patch-A", tmpdir, data)

                prune_history(index,
                              known_patch_count_before=4,
                              known_patch_count_after=3,
                              detected_obsolete_patches=[
                                                         'T-patch-9-F-patch-6.gz',
                                                         'T-patch-9-F-patch-7.gz',
                                                         'T-patch-9-F-patch-8.gz',
                                                         'T-patch-9-F-patch-9.gz',

                                                         'patch-7.gz',
                                                         ]
                              )

                delete_obsolete_patches(index)
                index.update_index()
else:
    @unittest.skip("Needs IsolatedAsyncioTestCase (python3 >= 3.8)")
    class TestPDiffs(unittest.TestCase):
        pass
