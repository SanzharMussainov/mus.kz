"""Download pinned browser assets to local static storage; run during development."""
import io
import tarfile
import urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'app'/'static'/'vendor'
root.mkdir(parents=True,exist_ok=True)
def fetch(url):
    return urllib.request.urlopen(url,timeout=60).read()
(root/'htmx.min.js').write_bytes(fetch('https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js'))
data=fetch('https://registry.npmjs.org/katex/-/katex-0.16.22.tgz')
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
    for member in archive.getmembers():
        name=member.name
        if not member.isfile(): continue
        relative=None
        if name.startswith('package/dist/'):
            relative=name.removeprefix('package/dist/')
            if relative not in ('katex.min.css','katex.min.js','contrib/auto-render.min.js') and not relative.startswith('fonts/'): continue
            relative=relative.replace('contrib/','')
        elif name=='package/LICENSE': relative='LICENSE'
        if relative:
            target=(root/'katex'/relative).resolve()
            if not target.is_relative_to(root.resolve()): raise RuntimeError('Unsafe path')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
(root/'HTMX-LICENSE').write_bytes(fetch('https://unpkg.com/htmx.org@2.0.4/LICENSE'))
print('HTMX and KaTeX stored locally.')
