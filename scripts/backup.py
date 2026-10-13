"""Consistent Docker Compose database + files backup without shell redirects."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from compose_tools import Compose, digest


def create_backup(compose, output):
    target = Path(output) / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    compose.run('exec', '-T', 'db', 'pg_isready', '-U', 'math', '-d', 'math')
    running = compose.run('ps', '--status', 'running', '--services', capture_output=True, text=True)
    web_running = 'web' in running.stdout.splitlines()
    target.mkdir(parents=True, exist_ok=False)
    if web_running:
        compose.run('stop', 'web')
    try:
        with (target / 'database.dump').open('wb') as out:
            compose.run('exec', '-T', 'db', 'pg_dump', '-U', 'math', '-d', 'math', '-Fc', stdout=out)
        with (target / 'files.tar').open('wb') as out:
            compose.run('run', '--rm', '--no-deps', '-T', 'web', 'tar', '-C', '/data/files', '-cf', '-', '.', stdout=out)
        manifest = {name: digest(target / name) for name in ('database.dump', 'files.tar')}
        (target / 'sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    finally:
        if web_running:
            compose.run('start', 'web')
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='backups')
    parser.add_argument('--project', help='Compose project; omitted means the current project')
    args = parser.parse_args()
    print(f'Backup: {create_backup(Compose(args.project), args.output).resolve()}')


if __name__ == '__main__':
    main()
