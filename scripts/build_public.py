"""Build the landing page without a database or running backend."""
import json
import os
import shutil
import time
from urllib.request import urlopen
from urllib.error import URLError
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]

def build(cabinet_url, output=None):
    url=urlsplit(cabinet_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        raise ValueError('CABINET_URL must be the HTTPS origin of your Render web service, without a path or credentials.')
    login=cabinet_url.rstrip('/')+'/login'
    source=os.environ.get('PUBLIC_CONTENT_URL','').strip()
    if source:
        parsed=urlsplit(source)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('PUBLIC_CONTENT_URL must be a public HTTPS URL without secrets.')
        for attempt in range(4):
            try:
                with urlopen(source,timeout=45) as response:
                    data=json.load(response)
                break
            except (URLError,TimeoutError):
                if attempt==3: raise RuntimeError('Public content endpoint unavailable; deployment stopped, previous site remains live.') from None
                time.sleep(5)
    else:
        data=json.loads((ROOT/'public/content.json').read_text(encoding='utf-8'))
    env=Environment(loader=FileSystemLoader(ROOT/'app/templates'),autoescape=select_autoescape(['html']))
    env.filters['date']=lambda value: datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Qyzylorda')).strftime('%d.%m.%Y · %H:%M') if value else '—'
    env.filters['label']=lambda value: {'subscription':'Из абонемента','separate':'Отдельная оплата','free':'Бесплатно'}.get(value,value)
    data['events']=[event for event in data['events'] if datetime.fromisoformat(event['starts_at'])>datetime.now(timezone.utc)]
    html=env.get_template('home.html').render(**data,user=None,public_only=True,static_site=True,cabinet_login_url=login)
    output=Path(output or ROOT/'dist-public')
    output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text(html,encoding='utf-8')
    # Copy only public assets, never app sources, configuration, or uploaded files.
    shutil.copytree(ROOT/'app/static',output/'static',dirs_exist_ok=True)
    (output/'robots.txt').write_text('User-agent: *\nAllow: /\n',encoding='utf-8')
    return output

if __name__=='__main__':
    print(build(os.environ.get('CABINET_URL','https://mus-kz.onrender.com')))
