"""Restore only into an explicitly named, empty Docker Compose project."""
import argparse
import json
from pathlib import Path, PurePosixPath
import tarfile
from compose_tools import Compose, digest


def validate_backup(source):
    source = Path(source)
    manifest = json.loads((source / 'sha256.json').read_text(encoding='utf-8'))
    for name in ('database.dump', 'files.tar'):
        if digest(source / name) != manifest.get(name):
            raise ValueError('Checksum mismatch: ' + name)
    with tarfile.open(source / 'files.tar') as archive:
        for entry in archive:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or not (entry.isfile() or entry.isdir()):
                raise ValueError('Unsafe file archive member.')
    return source


def restore_backup(compose, source):
    source = validate_backup(source)
    # Refuse before stopping anything; an accidental target must not be interrupted.
    result = compose.run('exec', '-T', 'db', 'psql', '-U', 'math', '-d', 'math', '-Atc',
                         "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
                         capture_output=True, text=True)
    if result.stdout.strip() != '0':
        raise ValueError('Refusing restore: database is not empty. Use a new Compose project.')
    result = compose.run('run', '--rm', '--no-deps', '-T', 'web', 'find', '/data/files', '-mindepth', '1', '-maxdepth', '1',
                         capture_output=True, text=True)
    if result.stdout.strip():
        raise ValueError('Refusing restore: file storage is not empty.')
    compose.run('stop', 'web')
    with (source / 'database.dump').open('rb') as inp:
        compose.run('exec', '-T', 'db', 'pg_restore', '-U', 'math', '-d', 'math', '--no-owner', '--exit-on-error', stdin=inp)
    with (source / 'files.tar').open('rb') as inp:
        compose.run('run', '--rm', '--no-deps', '-T', 'web', 'tar', '-C', '/data/files', '-xf', '-', stdin=inp)
    compose.run('up', '-d', 'web')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('backup')
    parser.add_argument('--project', required=True, help='New Compose project with an empty database and files')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    restore_backup(Compose(args.project, args.port), args.backup)
    print(f'Restored. Check http://127.0.0.1:{args.port}')


if __name__ == '__main__':
    main()
