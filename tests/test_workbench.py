"""Atomic SkillHub bundle contract through the real HTTP boundary."""
import base64
import hashlib
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from skillhub.api import deps
from skillhub.auth import create_token
from skillhub.config import AppConfig, StorageConfig
from skillhub.database import Database
from skillhub.main import app
from skillhub.storage import SkillStorage


@pytest_asyncio.fixture
async def hub(tmp_path):
    config = AppConfig(storage=StorageConfig(data_dir=tmp_path / 'data', skills_dir=tmp_path / 'skills'))
    db = Database(config.storage.data_dir / 'skillhub.db')
    await db.connect()
    storage = SkillStorage(config.storage.skills_dir)
    old = (deps._config, deps._db, deps._storage)
    deps._config, deps._db, deps._storage = config, db, storage
    admin = await db.create_user('bundle-admin', 'unused', 'admin')
    viewer = await db.create_user('bundle-reader', 'unused', 'viewer')
    headers = {'Authorization': 'Bearer ' + create_token(admin['id'], 'admin')}
    reader = {'Authorization': 'Bearer ' + create_token(viewer['id'], 'viewer')}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, db, storage, headers, reader
    deps._config, deps._db, deps._storage = old
    await db.close()


async def publish(client, headers, marker=b'old'):
    response = await client.post('/api/skills', headers=headers, data={'name': 'atomic', 'description': marker.decode()}, files=[('files', ('SKILL.md', marker)), ('files', ('scripts/run.bin', marker + b'\x00\xff')), ('files', ('references/api.md', marker))])
    assert response.status_code == 201
    return response.json()['id']


@pytest.mark.asyncio
async def test_bundle_full_sorted_authenticated_contract(hub):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    url = f'/api/workbench/skills/{skill_id}/bundle'
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={'Authorization': 'Bearer invalid'})).status_code == 401
    response = await client.get(url, headers=reader)
    assert response.status_code == 200
    bundle = response.json()
    assert bundle['id'] == skill_id and bundle['name'] == 'atomic' and bundle['description'] == 'old'
    assert [f['path'] for f in bundle['files']] == ['SKILL.md', 'references/api.md', 'scripts/run.bin']
    for f in bundle['files']:
        assert f['encoding'] == 'base64'
        content = base64.b64decode(f['content'])
        assert f['size'] == len(content)
        assert f['sha256'] == hashlib.sha256(content).hexdigest()
    digest_input = ''.join(f['path'] + '\0' + f['sha256'] + '\0' for f in bundle['files'])
    assert bundle['contentDigest'] == hashlib.sha256(digest_input.encode()).hexdigest()
    assert (await client.get('/api/workbench/skills/missing/bundle', headers=reader)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [False, True])
async def test_publication_remains_atomic_when_skills_directory_is_a_separate_mount(hub, monkeypatch, existing):
    import errno
    client, db, storage, headers, reader = hub
    previous_id = await publish(client, headers) if existing else None
    original = Path.rename

    def mounted_rename(source, target):
        # Docker deploys skills_dir as its own volume. Model the filesystem's
        # EXDEV boundary while exercising the actual publication endpoint.
        source_in_volume = source.is_relative_to(storage.skills_dir)
        target_in_volume = Path(target).is_relative_to(storage.skills_dir)
        if source_in_volume != target_in_volume:
            raise OSError(errno.EXDEV, 'Invalid cross-device link')
        return original(source, target)

    monkeypatch.setattr(Path, 'rename', mounted_rename)
    skill_id = await publish(client, headers, b'new')
    if existing:
        assert skill_id == previous_id
    response = await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)
    assert response.status_code == 200
    assert response.json()['description'] == 'new'
    assert [base64.b64decode(f['content']) for f in response.json()['files']] == [b'new', b'new', b'new\x00\xff']


@pytest.mark.asyncio
@pytest.mark.parametrize('filename', ['../escape', '/tmp/escape', 'scripts/../../escape', 'scripts\\escape', './SKILL.md', 'scripts//run'])
async def test_publish_rejects_unsafe_paths_before_mutating(hub, filename, tmp_path):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    if filename == '/tmp/escape':
        filename = str(tmp_path / 'absolute-escape')
    response = await client.post('/api/skills', headers=headers, data={'name': 'atomic', 'description': 'bad'}, files=[('files', ('SKILL.md', b'bad')), ('files', (filename, b'bad'))])
    assert response.status_code == 400
    assert (await db.get_skill(skill_id))['description'] == 'old'
    assert storage.get_skill_file(skill_id, 'SKILL.md') == b'old'


@pytest.mark.asyncio
async def test_bundle_rejects_symlink(hub, tmp_path):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    outside = tmp_path / 'secret'
    outside.write_bytes(b'secret')
    (storage._skill_path(skill_id) / 'references' / 'secret').symlink_to(outside)
    assert (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).status_code == 400


def _mutate_in_worker(data_dir, skills_dir, admin_id, skill_id, operation, entered, release, result):
    """Separate worker uses the actual HTTP publication/deletion endpoints."""
    import asyncio

    async def run():
        db = Database(Path(data_dir) / 'skillhub.db')
        await db.connect()
        deps._config = AppConfig(storage=StorageConfig(data_dir=Path(data_dir), skills_dir=Path(skills_dir)))
        deps._db, deps._storage = db, SkillStorage(Path(skills_dir))
        original = db.add_skill_file if operation == 'publish' else db.delete_skill

        async def pause(*args, **kwargs):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            return await original(*args, **kwargs)

        if operation == 'publish':
            db.add_skill_file = pause
        else:
            db.delete_skill = pause
        headers = {'Authorization': 'Bearer ' + create_token(admin_id, 'admin')}
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                if operation == 'publish':
                    await publish(client, headers, b'new')
                    result.put(201)
                else:
                    response = await client.delete(f'/api/skills/{skill_id}', headers=headers)
                    result.put(response.status_code)
        finally:
            await db.close()

    asyncio.run(run())


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['publish', 'delete'])
async def test_bundle_waits_for_whole_mutation_across_workers(hub, operation):
    import asyncio
    import multiprocessing
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    ctx = multiprocessing.get_context('spawn')
    entered, release, result = ctx.Event(), ctx.Event(), ctx.Queue()
    admin = await db.get_user_by_username('bundle-admin')
    worker = ctx.Process(target=_mutate_in_worker, args=(str(db.db_path.parent), str(storage.skills_dir), admin['id'], skill_id, operation, entered, release, result))
    worker.start()
    request = None
    try:
        assert await asyncio.to_thread(entered.wait, 10), 'Worker did not reach partial mutation'
        request = asyncio.create_task(client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader))
        await asyncio.sleep(0.15)
        assert not request.done(), 'Bundle observed mutation before worker finished'
        release.set()
        response = await asyncio.wait_for(request, 10)
        if operation == 'delete':
            assert response.status_code == 404
        else:
            assert response.status_code == 200
            bundle = response.json()
            assert bundle['description'] == 'new'
            assert [base64.b64decode(f['content']) for f in bundle['files']] == [b'new', b'new', b'new\x00\xff']
        await asyncio.to_thread(worker.join, 10)
        assert worker.exitcode == 0
        assert result.get(timeout=1) == (201 if operation == 'publish' else 204)
    finally:
        release.set()
        if request and not request.done():
            request.cancel()
        if worker.is_alive():
            worker.terminate()
            await asyncio.to_thread(worker.join, 5)
        result.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['SKILL.md', 'references', '.'])
async def test_bundle_rejects_symlinked_files_directories_and_root(hub, tmp_path, target):
    import shutil
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'SKILL.md').write_bytes(b'private')
    link = storage._skill_path(skill_id) / target
    if link.is_dir():
        shutil.rmtree(link)
        link.symlink_to(outside, target_is_directory=True)
    else:
        link.unlink()
        link.symlink_to(outside / 'SKILL.md')
    assert (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).status_code == 400


@pytest.mark.asyncio
async def test_missing_skill_document_is_unavailable(hub):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    (storage._skill_path(skill_id) / 'SKILL.md').unlink()
    assert (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).status_code == 404


@pytest.mark.asyncio
async def test_same_worker_waiting_reader_does_not_deadlock_publish(hub, monkeypatch):
    import asyncio
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    entered, release = asyncio.Event(), asyncio.Event()
    original = db.add_skill_file

    async def pause(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(db, 'add_skill_file', pause)
    writer = asyncio.create_task(publish(client, headers, b'new'))
    await asyncio.wait_for(entered.wait(), 3)
    request = asyncio.create_task(client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader))
    try:
        await asyncio.sleep(0.03)
        assert not request.done()
    finally:
        release.set()
    await asyncio.wait_for(writer, 3)
    response = await asyncio.wait_for(request, 3)
    assert response.status_code == 200
    assert response.json()['description'] == 'new'


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [True, False])
async def test_failed_publication_preserves_complete_previous_state(hub, monkeypatch, existing):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers) if existing else None
    before = None
    previous_metadata = await db.get_skill(skill_id) if existing else None
    previous_files = await db.get_skill_files(skill_id) if existing else []
    if existing:
        before = (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).json()
    original = db.add_skill_file
    writes = 0

    async def fail_second_file(*args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError('Injected publication failure')
        return await original(*args, **kwargs)

    monkeypatch.setattr(db, 'add_skill_file', fail_second_file)
    failed_transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=failed_transport, base_url='http://test') as failed_client:
        response = await failed_client.post('/api/skills', headers=headers, data={'name': 'atomic', 'description': 'new'}, files=[('files', ('SKILL.md', b'new')), ('files', ('scripts/run.bin', b'new'))])
    assert response.status_code == 500
    if existing:
        after = (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).json()
        assert after == before
        assert await db.get_skill(skill_id) == previous_metadata
        assert await db.get_skill_files(skill_id) == previous_files
    else:
        assert await db.get_skill_by_name('atomic') is None


@pytest.mark.asyncio
async def test_failed_staging_keeps_previous_publication(hub, monkeypatch):
    client, db, storage, headers, reader = hub
    skill_id = await publish(client, headers)
    before = (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).json()
    previous_metadata = await db.get_skill(skill_id)
    previous_files = await db.get_skill_files(skill_id)
    original = Path.write_bytes
    writes = 0

    def fail_second_staged_write(path, content):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError('Injected staged file failure')
        return original(path, content)

    monkeypatch.setattr(Path, 'write_bytes', fail_second_staged_write)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test') as failing_client:
        response = await failing_client.post('/api/skills', headers=headers, data={'name': 'atomic', 'description': 'new'}, files=[('files', ('SKILL.md', b'new')), ('files', ('scripts/run.bin', b'new'))])
    assert response.status_code == 500
    assert (await client.get(f'/api/workbench/skills/{skill_id}/bundle', headers=reader)).json() == before
    assert await db.get_skill(skill_id) == previous_metadata
    assert await db.get_skill_files(skill_id) == previous_files
