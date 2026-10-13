import io
import json
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compose_tools import digest
from restore import restore_backup, validate_backup
from backup import create_backup


def archive(tmp_path, name='./control.png', link=False):
    (tmp_path/'database.dump').write_bytes(b'PGDMP-test')
    with tarfile.open(tmp_path/'files.tar','w') as tar:
        entry=tarfile.TarInfo(name)
        if link:
            entry.type=tarfile.SYMTYPE;entry.linkname='/etc/passwd';tar.addfile(entry)
        else:
            entry.size=4;tar.addfile(entry,io.BytesIO(b'test'))
    (tmp_path/'sha256.json').write_text(json.dumps({name:digest(tmp_path/name) for name in ('database.dump','files.tar')}))
    return tmp_path


def test_corrupt_backup_rejected_before_docker(tmp_path):
    source=archive(tmp_path);(source/'database.dump').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='Checksum'): validate_backup(source)


@pytest.mark.parametrize('name,link',[('../outside',False),('/outside',False),('./link',True)])
def test_unsafe_file_archive_rejected(tmp_path,name,link):
    with pytest.raises(ValueError,match='Unsafe'): validate_backup(archive(tmp_path,name,link))


def test_nonempty_database_is_not_stopped(tmp_path):
    calls=[]
    class FakeCompose:
        def run(self,*args,**kwargs):
            calls.append(args);return SimpleNamespace(stdout='21\n')
    with pytest.raises(ValueError,match='database is not empty'):
        restore_backup(FakeCompose(),archive(tmp_path))
    assert len(calls)==1 and calls[0][0]=='exec'


def test_nonempty_storage_not_overwritten(tmp_path):
    calls=[]
    class FakeCompose:
        def run(self,*args,**kwargs):
            calls.append(args);return SimpleNamespace(stdout='0\n' if len(calls)==1 else '/data/files/existing\n')
    with pytest.raises(ValueError,match='storage is not empty'):
        restore_backup(FakeCompose(),archive(tmp_path))
    assert not any(call[0] in ('stop','up') for call in calls)


@pytest.mark.parametrize('running',[True,False])
def test_backup_preserves_initial_web_state_on_failure(tmp_path,running):
    calls=[]
    class FakeCompose:
        def run(self,*args,**kwargs):
            calls.append(args)
            if 'pg_dump' in args: raise RuntimeError('disk failure')
            return SimpleNamespace(stdout='db\nweb\n' if running else 'db\n')
    with pytest.raises(RuntimeError,match='disk failure'):
        create_backup(FakeCompose(),tmp_path)
    assert (('start','web') in calls)==running
    assert (('stop','web') in calls)==running
