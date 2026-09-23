import hashlib, json, os, pathlib, stat, sys, tempfile
sys.path.insert(0, r'C:\NovaInput')
from nova_release_policy import SnapshotPolicy, SnapshotClass, scan_workspace
base = pathlib.Path(r'C:\NovaInput')
plan = json.loads((base / 'plan.json').read_text())
result = dict(schema_version=1, run_id=plan['run_id'], nonce=plan['nonce'],
              backend='windows_sandbox', passed=False)
try:
    hashes = {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
              for name in plan['payload_sha256']}
    assert hashes == plan['payload_sha256'], 'guest payload hashes differ'
    with tempfile.TemporaryDirectory(prefix='nova-symlink-') as temp:
        temp = pathlib.Path(temp)
        repo = temp / 'repo'
        assets = repo / 'assets'
        assets.mkdir(parents=True)
        external = temp / 'external'
        external.mkdir()
        (external / 'sentinel.txt').write_text('must not be scanned', encoding='utf-8')
        link = assets / 'linked'
        link.symlink_to(external, target_is_directory=True)
        tag = link.lstat().st_reparse_tag
        assert os.name == 'nt' and tag == stat.IO_REPARSE_TAG_SYMLINK
        assert link.is_symlink() and link.is_dir()
        policy = SnapshotPolicy.load(base / 'policy.json')
        report = scan_workspace(repo, policy, tracked_paths=set(), deleted_paths=set())
        paths = [item.path for item in report.decisions]
        assert paths == ['assets/linked'], paths
        assert report.decisions[0].classification is SnapshotClass.AMBIGUOUS
        assert report.decisions[0].rule == 'filesystem_link_requires_boundary_check'
        assert 'assets/linked/sentinel.txt' not in paths
        result.update(passed=True, payload_sha256=hashes, reparse_tag=tag,
                      paths=paths, classification=report.decisions[0].classification.value,
                      rule=report.decisions[0].rule, sentinel_scanned=False)
except Exception as exc:
    result['error'] = repr(exc)
out = pathlib.Path(r'C:\NovaOutput')
(out / 'result.tmp').write_text(json.dumps(result), encoding='utf-8')
(out / 'result.tmp').replace(out / 'result.json')
