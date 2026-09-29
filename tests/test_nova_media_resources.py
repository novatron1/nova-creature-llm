"""A second stage must not bypass a lease, quarantine or measured headroom."""
from concurrent.futures import ThreadPoolExecutor
from nova_gateway.media_store import MediaStore


def gate(tmp_path):
    from nova_gateway.media_resources import ResourceGate
    return ResourceGate(tmp_path, MediaStore(tmp_path / 'jobs.db'))


def test_only_one_concurrent_lease_and_no_foreign_release(tmp_path):
    resource = gate(tmp_path)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(resource.acquire, [str(n) for n in range(8)]))
    assert sum(results) == 1
    winner = str(results.index(True))
    resource.release('foreign')
    assert not resource.acquire('new')
    resource.release(winner)
    assert resource.acquire('new')


def test_headroom_and_unknown_measurements_fail_closed(tmp_path, monkeypatch):
    from nova_gateway.media_resources import ResourceSnapshot
    resource = gate(tmp_path)
    snapshot = ResourceSnapshot(6*1024**3, 10*1024**3+99, 6*1024**3, 'now')
    monkeypatch.setattr(resource, 'snapshot', lambda: snapshot)
    assert resource.admit(100, 4*1024**3)[0] is False
    assert resource.admit(99, 4*1024**3)[0] is True
    assert resource.admit(99, 7*1024**3)[0] is False
    assert resource.admit(99, 0)[0] is False  # no established memory profile
    snapshot = ResourceSnapshot(None, 20*1024**3, None, 'now')
    assert resource.admit(99, 4*1024**3)[0] is False


def test_quarantine_survives_reopen_and_blocks_acquisition(tmp_path):
    resource = gate(tmp_path)
    resource.store.set_quarantine('lost worker custody')
    reopened = gate(tmp_path)
    assert not reopened.acquire('next')
    assert reopened.admit(0, 1)[0] is False
    reopened.store.set_quarantine(None)
    assert reopened.acquire('next')


def test_active_lease_survives_restart_and_separate_gate_instances(tmp_path):
    first = gate(tmp_path)
    assert first.acquire('existing-generation')
    second = gate(tmp_path)
    assert not second.acquire('new-generation')
    second.release('wrong-owner')
    assert not first.acquire('new-generation')
    second.release('existing-generation')
    assert first.acquire('new-generation')
