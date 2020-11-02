import contextlib
import os
import shutil
import tempfile

from base_test import DakTestCase

from daklib.pdiff import PDiffIndex


def generate_patch(index, patch_name, content_dir, new_content):
    new_file = os.path.join(content_dir, "data-current")
    orig_file = os.path.join(content_dir, "data-previous")

    if os.path.isfile(new_file):
        os.rename(new_file, orig_file)
    elif not os.path.isfile(orig_file):
        # Ensure there is an empty orig file
        with open(orig_file, 'w'):
            pass

    with open(new_file, 'wt') as fd:
        if isinstance(new_content, list):
            fd.writelines("{}\n".format(line) for line in new_content)
        else:
            fd.write(new_content)
    index.generate_and_add_patch_file(orig_file, new_file, patch_name)


def prune_history(index, known_patch_count_before=None, known_patch_count_after=None, detected_obsolete_patches=None):

    if known_patch_count_before is not None:
        assert len(index.history) == known_patch_count_before
    index.prune_patch_history()
    if known_patch_count_after is not None:
        assert len(index.history) == known_patch_count_after
    if detected_obsolete_patches is not None:
        assert sorted(os.path.basename(p) for p in index.find_obsolete_patches()) == detected_obsolete_patches


def delete_obsolete_patches(index):
    for patch_file in index.find_obsolete_patches():
        os.unlink(patch_file)


def reload_and_compare_pdiff_indices(index):
    reloaded_index = PDiffIndex(index.patches_dir, index.max)
    assert index.history_order == reloaded_index.history_order
    assert index.history == reloaded_index.history
    assert index.filesizehashes == reloaded_index.filesizehashes
    assert index.can_path == reloaded_index.can_path


@contextlib.contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


class TestPDiffs(DakTestCase):

    def test_pdiff_index(self):
        with tempdir() as tmpdir:
            pdiff_dir = os.path.join(tmpdir, "pdiffs")
            index_file = os.path.join(pdiff_dir, 'Index')
            index = PDiffIndex(pdiff_dir, 3)

            data = [
                'Version 1',
                'Some',
                'data',
                'across',
                '6',
                'lines',
            ]

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
