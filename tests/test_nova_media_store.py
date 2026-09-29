"""Real SQLite custody regressions: cross-owner access, replay and lost updates."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from nova_gateway.errors import InvalidRequestError, PermissionDeniedError


@pytest.fixture
def store_type():
    # Import inside fixture keeps the first RED a named missing-feature failure.
    import importlib.util
    assert importlib.util.find_spec('nova_gateway.media_store'), 'Persistent media store is missing'
    from nova_gateway.media_store import MediaStore
    return MediaStore


def test_request_key_is_owner_scoped_and_content_bound(tmp_path, store_type):
    from nova_gateway.media_store import MediaConflictError
    store = store_type(tmp_path / 'media.sqlite3')
    request = {'prompt': 'nod', 'seed': 3}
    first = store.create_job('alice', 'click-1', request)
    assert store.create_job('alice', 'click-1', {'seed': 3, 'prompt': 'nod'}).id == first.id
    request['seed'] = 5
    assert store.get_job(first.id, 'alice').request['seed'] == 3
    with pytest.raises(MediaConflictError):
        store.create_job('alice', 'click-1', request)
    with pytest.raises(PermissionDeniedError):
        store.get_job(first.id, 'bob')
    assert store.create_job('bob', 'click-1', request).id != first.id
    assert [j.id for j in store.list_jobs('alice')] == [first.id]


def test_reopen_preserves_stage_and_quarantine(tmp_path, store_type):
    store = store_type(tmp_path / 'media.sqlite3')
    job = store.create_job('alice', '1', {})
    store.transition(job.id, 'queued', 'preparing', backend_id='wan_studio_8190')
    store.transition(job.id, 'preparing', 'failed', error='render failed', cleanup_error='release uncertain')
    store.set_quarantine('release uncertain')
    reopened = store_type(tmp_path / 'media.sqlite3')
    result = reopened.get_job(job.id, 'alice')
    assert result.stage == 'failed'
    assert result.error == 'render failed'
    assert result.cleanup_error == 'release uncertain'
    assert result.backend_id == 'wan_studio_8190'
    assert reopened.get_quarantine() == 'release uncertain'
    reopened.set_quarantine(None)
    assert store.get_quarantine() is None


def test_compare_and_swap_transition_has_one_winner(tmp_path, store_type):
    from nova_gateway.media_store import MediaConflictError
    path = tmp_path / 'media.sqlite3'
    store = store_type(path)
    job = store.create_job('alice', '1', {})
    barrier = Barrier(2)
    def transition():
        concurrent = store_type(path)
        barrier.wait(timeout=5)
        try:
            return concurrent.transition(job.id, 'queued', 'preparing').stage
        except MediaConflictError:
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: transition(), range(2)))
    assert sorted(results) == ['conflict', 'preparing']
    assert store.get_job(job.id, 'alice').stage == 'preparing'


def test_invalid_transition_and_field_cannot_mutate_job(tmp_path, store_type):
    store = store_type(tmp_path / 'media.sqlite3')
    job = store.create_job('alice', '1', {})
    with pytest.raises(InvalidRequestError):
        store.transition(job.id, 'queued', 'completed')
    with pytest.raises(InvalidRequestError):
        store.transition(job.id, 'queued', 'preparing', owner_id='bob')
    assert store.get_job(job.id, 'alice').stage == 'queued'


def test_assets_are_owned_immutable_and_persistent(tmp_path, store_type):
    from nova_gateway.media_store import AssetRecord, MediaConflictError
    store = store_type(tmp_path / 'media.sqlite3')
    asset = AssetRecord('asset-1', 'alice', 'image', 'inputs/images/a.png', 'a'*64, 40, {'width': 2})
    store.register_asset(asset)
    with pytest.raises(MediaConflictError):
        store.register_asset(asset)
    with pytest.raises(PermissionDeniedError):
        store.get_asset(asset.id, 'bob')
    record = store_type(tmp_path / 'media.sqlite3').get_asset(asset.id, 'alice')
    record.metadata['width'] = 999
    assert store.get_asset(asset.id, 'alice').metadata['width'] == 2


@pytest.mark.parametrize('owner,key,payload', [('', '1', {}), ('a', '', {}), ('a', '1', {'bad': float('nan')})])
def test_invalid_identity_or_nonfinite_request_rejected(tmp_path, store_type, owner, key, payload):
    with pytest.raises(InvalidRequestError):
        store_type(tmp_path / 'media.sqlite3').create_job(owner, key, payload)
