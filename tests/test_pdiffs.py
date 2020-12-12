import contextlib
import os
import shutil
import tempfile

from base_test import DakTestCase

from daklib.pdiff import PDiffIndex


def generate_orig(content_dir, initial_content):
    current_file = os.path.join(content_dir, "data-current")
    with open(current_file, 'wt') as fd:
        if isinstance(initial_content, list):
            fd.writelines("{}\n".format(line) for line in initial_content)
        else:
            fd.write(initial_content)


def generate_patch(index, patch_name, content_dir, new_content):
    new_file = os.path.join(content_dir, "data-current")
    orig_file = os.path.join(content_dir, "data-previous")

    if os.path.isfile(new_file):
        os.rename(new_file, orig_file)
    elif not os.path.isfile(orig_file):
        # Ensure there is an empty orig file
        with open(orig_file, 'w'):
            pass

    generate_orig(content_dir, new_content)

    index.generate_and_add_patch_file(orig_file, new_file, patch_name)


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


class TestPDiffs(DakTestCase):

    def test_pdiff_index_unmerged(self):
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
            generate_patch(index, "patch-1", tmpdir, data)
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
            generate_patch(index, "patch-2", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=2,
                          known_patch_count_after=2,
                          detected_obsolete_patches=[]
                          )

            data[2] = 'Text'

            generate_patch(index, "patch-3", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=3,
                          known_patch_count_after=3,
                          detected_obsolete_patches=[]
                          )

            data[0] = 'Version 3'

            generate_patch(index, "patch-4", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=4,
                          known_patch_count_after=3,
                          detected_obsolete_patches=['patch-1.gz']
                          )

            data[0] = 'Version 4'
            data[-1] = 'lines.'

            generate_patch(index, "patch-5", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=4,
                          known_patch_count_after=3,
                          detected_obsolete_patches=['patch-1.gz', 'patch-2.gz']
                          )

            index.update_index()
            reload_and_compare_pdiff_indices(index)

            delete_obsolete_patches(index)

    def test_pdiff_index_merged(self):
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
            generate_patch(index, "patch-1", tmpdir, data)
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
            generate_patch(index, "patch-2", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=2,
                          known_patch_count_after=2,
                          detected_obsolete_patches=[]
                          )

            data[2] = 'Text'

            generate_patch(index, "patch-3", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=3,
                          known_patch_count_after=3,
                          detected_obsolete_patches=[]
                          )

            data[0] = 'Version 3'

            generate_patch(index, "patch-4", tmpdir, data)

            prune_history(index,
                          known_patch_count_before=4,
                          known_patch_count_after=3,
                          detected_obsolete_patches=['T-patch-1-F-patch-1.gz', 'patch-1.gz']
                          )

            data[0] = 'Version 4'
            data[-1] = 'lines.'

            generate_patch(index, "patch-5", tmpdir, data)

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

            generate_patch(index, "patch-6", tmpdir, data)

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

            generate_patch(index, "patch-7", tmpdir, data)

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
            generate_patch(index, "patch-8", tmpdir, data)

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
            generate_patch(index, "patch-9", tmpdir, data)

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
            generate_patch(index, "patch-A", tmpdir, data)

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
