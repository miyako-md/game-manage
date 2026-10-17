import json

import pytest

from scripts.cloud.package_release import PackageError, write_build_metadata


def test_release_metadata_records_only_the_pinned_source_identity(tmp_path):
    (tmp_path / 'src/game_assistant').mkdir(parents=True)
    commit = 'a' * 40
    write_build_metadata(tmp_path, commit)
    assert json.loads((tmp_path / 'src/game_assistant/build-info.json').read_text()) == {
        'schema': 1, 'source': 'miyako-md/game-manage', 'commit': commit,
    }


@pytest.mark.parametrize('revision', ['main', 'a' * 39, '../main', ''])
def test_release_metadata_rejects_unpinned_revisions(tmp_path, revision):
    with pytest.raises(PackageError, match='full_commit_sha_required'):
        write_build_metadata(tmp_path, revision)
    assert not (tmp_path / 'src').exists()
