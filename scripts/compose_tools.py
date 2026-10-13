"""Explicit Compose project selection for non-destructive backup rehearsals."""
import hashlib
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Compose:
    def __init__(self, project=None, port=None):
        if project and not re.fullmatch(r'[a-z0-9][a-z0-9_-]+', project):
            raise ValueError('Project name must contain lowercase letters, digits, _ or -.')
        self.command = ['docker', 'compose'] + (['-p', project] if project else [])
        self.env = os.environ.copy()
        if port is not None:
            if not 1024 <= port <= 65535:
                raise ValueError('Port must be between 1024 and 65535.')
            self.env['WEB_PORT'] = str(port)

    def run(self, *args, **kwargs):
        return subprocess.run(self.command + list(args), cwd=ROOT, env=self.env, check=True, **kwargs)
