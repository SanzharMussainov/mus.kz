from datetime import timedelta
from app.db import now
from app.models import Meeting
from app.export_public import export
from scripts.build_public import build
import pytest


def test_export_is_public_allowlist(db,data):
    data['course'].public=True
    data['g1'].meet_url='https://meet.google.com/private-meeting'
    db.add(Meeting(title='Private event',is_event=True,public=False,starts_at=now()+timedelta(days=2),duration=60))
    db.commit()
    result=export(db)
    assert len(result['courses'])==1
    assert len(result['groups'])==2
    assert result['events']==[]
    assert 'meet_url' not in result['groups'][0]
    assert set(result)=={'settings','courses','groups','events'}
    assert 'password_hash' not in str(result)


def test_static_build_has_no_backend_requests(tmp_path,monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    output=build('https://cabinet.example.com',tmp_path)
    html=(output/'index.html').read_text(encoding='utf-8')
    assert 'https://cabinet.example.com/login' in html
    assert 'href="/login"' not in html
    assert '<form' not in html and 'csrf' not in html
    assert (output/'static/teacher.jpg').is_file()
    assert (output/'static/logo.jpg').is_file()
    assert not (output/'.env').exists()
    with pytest.raises(ValueError): build('https://user:secret@example.com',tmp_path)
    with pytest.raises(ValueError): build('',tmp_path)
