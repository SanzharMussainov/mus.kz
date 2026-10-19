import json
import pytest
from conftest import login, token
from app.models import Settings
from scripts.build_public import build


def test_public_endpoint_and_publish_permissions(client,db,data,monkeypatch):
    data['course'].public=True;db.commit()
    response=client.get('/public-content.json')
    assert response.status_code==200 and len(response.json()['courses'])==1
    assert 'password_hash' not in response.text and 'meet_url' not in response.text
    login(client,'alice')
    assert client.post('/admin/publish-public',data={'csrf':token(client,'/dashboard')}).status_code==403
    login(client,'admin')
    assert client.post('/admin/publish-public',data={}).status_code==403
    calls=[]
    async def trigger(): calls.append(True)
    monkeypatch.setattr('app.main.trigger_public_deploy',trigger)
    response=client.post('/admin/publish-public',data={'csrf':token(client,'/dashboard')})
    assert response.status_code==200 and 'Публикация запущена.' in response.text
    assert len(calls)==1
    assert client.post('/admin/publish-public',data={'csrf':token(client,'/dashboard')}).status_code==400
    assert len(calls)==1


def test_build_loads_current_public_data(client,db,data,tmp_path,monkeypatch):
    from io import BytesIO
    settings=db.get(Settings,1);settings.headline='Fresh public headline';db.commit()
    payload=client.get('/public-content.json').content
    monkeypatch.setenv('PUBLIC_CONTENT_URL','https://cabinet.example/public-content.json')
    monkeypatch.setattr('scripts.build_public.urlopen',lambda *a,**kw:BytesIO(payload))
    build('https://cabinet.example',tmp_path)
    assert 'Fresh public headline' in (tmp_path/'math'/'index.html').read_text(encoding='utf-8')


def test_hook_not_configured_does_not_report_success(client,data,monkeypatch):
    monkeypatch.delenv('PUBLIC_DEPLOY_HOOK',raising=False)
    login(client,'admin')
    response=client.post('/admin/publish-public',data={'csrf':token(client,'/dashboard')})
    assert response.status_code==400 and 'Публикация не настроена' in response.text
