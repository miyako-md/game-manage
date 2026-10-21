"""Operator-selected public branch cannot be widened by a web request."""
import hashlib
from types import SimpleNamespace

import pytest
import respx
from pydantic import ValidationError

from game_assistant.config import Settings
from game_assistant.system_update import SystemUpdateService, GITHUB_ROOT, UpstreamError
from game_assistant.system_update_protocol import read_json, write_json_atomic
from game_assistant.system_update_version import capture_version
from game_assistant.system_update_worker import Updater, UpdateError, LinuxPlatform, release_identity
from tests.test_system_update_version import marker, SHA, OTHER

BRANCH = 'codex/cloud-qq-public'


@pytest.mark.parametrize('ref', ['main', 'codex%2Fcloud-qq-public'])
def test_real_fetch_accepts_only_fixed_operator_commit_endpoints(ref):
    url = GITHUB_ROOT + '/commits/' + ref
    with respx.mock(assert_all_called=True) as network:
        network.get(url).respond(200, json={'sha': OTHER})
        assert SystemUpdateService._fetch(url) == {'sha': OTHER}


@pytest.mark.parametrize('url', [GITHUB_ROOT + '/commits/feature%2Funreviewed',
    'https://api.github.com/repos/other/repository/commits/main', GITHUB_ROOT + '/commits/main?redirect=elsewhere'])
def test_real_fetch_rejects_unapproved_urls_before_network(url):
    with respx.mock(assert_all_called=True):
        with pytest.raises(UpstreamError, match='github_invalid_response'): SystemUpdateService._fetch(url)


@pytest.fixture
def public_service(tmp_path):
    root = marker(tmp_path / 'installation')
    record = read_json(root / 'release.json'); record['branch'] = BRANCH
    write_json_atomic(root / 'release.json', record)
    state = tmp_path / 'state'; state.mkdir()
    write_json_atomic(state / 'worker.json', {'schema': 1, 'pid': 123, 'platform': 'linux', 'branch': BRANCH, 'updated_at': 2000})
    urls = []
    def fetch(url):
        urls.append(url)
        if '/commits/' in url:
            return {'sha': OTHER, 'commit': {'message': 'public next', 'committer': {'date': '2026-10-18T00:00:00Z'}}}
        return {'status': 'ahead', 'base_commit': {'sha': SHA}, 'merge_base_commit': {'sha': SHA}, 'ahead_by': 1, 'behind_by': 0}
    service = SystemUpdateService(Settings(system_update_enabled=True, system_update_branch=BRANCH,
        system_update_install_root=str(root), system_update_state_dir=str(state)),
        version=capture_version(root), fetch=fetch, clock=lambda: 2000, platform_name='linux')
    return service, state, urls


def test_public_branch_check_and_queue_use_only_operator_policy(public_service):
    service, state, urls = public_service
    result = service.check()
    assert urls[0] == GITHUB_ROOT + '/commits/codex%2Fcloud-qq-public'
    assert result['branch'] == BRANCH and result['can_apply']
    service.apply(SHA, OTHER)
    assert read_json(state / 'request.json')['source'] == BRANCH


def test_a_helper_for_another_branch_cannot_enable_apply(public_service):
    service, state, _ = public_service
    write_json_atomic(state / 'worker.json', {'schema': 1, 'pid': 123, 'platform': 'linux', 'branch': 'main', 'updated_at': 2000})
    assert service.check()['unavailable_reason'] == 'worker_unavailable'
    assert not (state / 'request.json').exists()


def test_unpublished_current_is_not_an_update_candidate(public_service):
    service, state, _ = public_service
    original = service.fetch
    def fetch(url):
        if '/compare/' in url:
            return {'status': 'behind', 'base_commit': {'sha': SHA}, 'merge_base_commit': {'sha': OTHER}, 'ahead_by': 0, 'behind_by': 1}
        return original(url)
    service.fetch = fetch
    result = service.check()
    assert result['unavailable_reason'] == 'current_ahead' and not result['can_apply']
    assert not (state / 'request.json').exists()


@pytest.mark.parametrize('branch', ['feature/unreviewed', 'main;id', 'https://other.invalid/repo', '../main'])
def test_api_configuration_rejects_unapproved_sources(branch):
    with pytest.raises(ValidationError): Settings(system_update_branch=branch)


def test_public_release_identity_is_valid_but_cannot_cross_operator_policy(public_service):
    service, _, _ = public_service
    assert service.version.ready
    assert release_identity(service.version.root, branch=BRANCH) == SHA
    with pytest.raises(UpdateError, match='invalid_release_manifest'):
        release_identity(service.version.root, branch='main')


def test_worker_fetches_public_ref_from_fixed_repository_without_using_request_source(tmp_path):
    worker = object.__new__(Updater)
    worker.config = SimpleNamespace(branch=BRANCH)
    worker.private = tmp_path
    seen = []
    def run(argv, **kwargs):
        if 'fetch' in argv:
            seen.extend(str(arg) for arg in argv)
            raise UpdateError('probe_before_network')
        return SimpleNamespace(returncode=0, stdout='')
    worker.run = run
    with pytest.raises(UpdateError, match='probe_before_network'): worker.prepare(SHA, OTHER)
    assert 'https://github.com/miyako-md/game-manage.git' in seen
    assert 'refs/heads/codex/cloud-qq-public:refs/remotes/official/main' in seen
    assert 'refs/heads/main:refs/remotes/official/main' not in seen


def test_managed_update_retains_public_render_assets_without_copying_old_entrypoints_or_private_files(tmp_path):
    old = tmp_path / 'old'; release = tmp_path / 'new'
    for root in [old, release]: (root / 'frontend/dist/assets').mkdir(parents=True)
    previous = old / 'frontend/dist'; target = release / 'frontend/dist'
    (previous / 'assets/old.js').write_text('old public chunk')
    (previous / 'assets/shared.css').write_text('old css')
    (target / 'assets/shared.css').write_text('new css')
    (previous / 'local-game-icons').mkdir(); (previous / 'local-game-icons/nte.png').write_bytes(b'public icon')
    (previous / 'assets/stale.js').write_text('carried from an older release')
    (previous / 'index.html').write_text('old entrypoint <script src="/assets/old.js"></script><link href="/assets/shared.css">')
    (target / 'index.html').write_text('new entrypoint')
    (previous / 'credentials.json').write_text('never copy')
    font = tmp_path / 'font.otf'; font.write_bytes(b'configured font')
    (previous / 'render-font.woff2').write_bytes(b'wOF2verified-font')
    write_json_atomic(previous / 'render-font.json', {
        'source_sha256': hashlib.sha256(font.read_bytes()).hexdigest(),
        'woff2_sha256': hashlib.sha256(b'wOF2verified-font').hexdigest()})
    platform = object.__new__(LinuxPlatform)
    platform.previous = old; platform.runtime_data = {'qq_image_font_path': str(font)}
    platform.retain_render_assets(release)
    assert (target / 'assets/old.js').read_text() == 'old public chunk'
    # Only chunks the previous release's own pages reference are carried; older leftovers drop out.
    assert not (target / 'assets/stale.js').exists()
    assert (target / 'assets/shared.css').read_text() == 'new css'
    assert (target / 'local-game-icons/nte.png').read_bytes() == b'public icon'
    assert (target / 'render-font.woff2').read_bytes() == b'wOF2verified-font'
    assert (target / 'index.html').read_text() == 'new entrypoint'
    assert not (target / 'credentials.json').exists()
