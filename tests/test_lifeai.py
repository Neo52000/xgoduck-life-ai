"""Offline tests: no remote API, external robot hardware, or internet required."""
import base64
import io
import os
import tempfile
from pathlib import Path

# The module includes a production ASGI app created at import time; use test-only secrets.
os.environ.setdefault('ADMIN_USER','admin')
os.environ.setdefault('ADMIN_PASSWORD','test-admin-password-example')
os.environ.setdefault('ROBOT_API_KEY','test-robot-api-key-123456789123456')
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/lifeai_test_import.sqlite3')
os.environ.setdefault('DATA_DIR','/tmp/lifeai_test_import_media')

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from lifeai.app import create_app
from lifeai.config import Settings


def jpg(color='red'):
    im=Image.new('RGB',(200,150),'white')
    d=ImageDraw.Draw(im)
    d.rectangle((30,40,160,125),fill=color)
    buff=io.BytesIO()
    im.save(buff,'JPEG',quality=90)
    return buff.getvalue()


@pytest.fixture()
def env(tmp_path):
    cfg=Settings(database_url=f'sqlite:///{tmp_path / "memory.sqlite3"}',
                 data_dir=tmp_path / 'media',admin_user='admin',
                 admin_password='test-admin-password-example',
                 robot_api_key='test-robot-api-key-123456789123456')
    app=create_app(cfg)
    header='Basic '+base64.b64encode(b'admin:test-admin-password-example').decode()
    with TestClient(app) as client:
        yield client, {'Authorization':header}, cfg
    app.state.engine.dispose()


def upload(client, headers, data=None, mimetype='image/jpeg'):
    return client.post('/api/observations',files={'file':('test.jpg',data if data is not None else jpg(),mimetype)},headers=headers)


def test_health_auth_and_image_limits(env):
    client, headers, cfg=env
    assert client.get('/health').json()['motors']=='disabled'
    assert client.get('/api/state').status_code==401
    assert client.get('/').status_code==401
    assert client.get('/api/state',headers={'X-Robot-Key':cfg.robot_api_key}).status_code==200
    assert client.get('/').status_code==401 or client.get('/',headers=headers).status_code==200
    assert upload(client,headers,b'fake image').status_code==422
    assert upload(client,headers,b'a'*(cfg.max_image_bytes+1)).status_code==413
    assert upload(client,headers,jpg(),mimetype='application/pdf').status_code==415


def test_learning_then_visual_recall_and_deletion(env):
    client,headers,cfg=env
    first=upload(client,headers)
    assert first.status_code==201,first.text
    obs=first.json()
    assert obs['status']=='unknown'
    assert client.get(obs['image_url'],headers=headers).status_code==200
    confirm=client.post(f"/api/observations/{obs['id']}/confirm",headers=headers,
                        json={'label':'Agrafeuse','category':'papeterie','description':'Assemble des feuilles'})
    assert confirm.status_code==200,confirm.text
    cid=confirm.json()['concept']['id']
    detail=client.get(f'/api/concepts/{cid}',headers=headers).json()
    assert detail['example_count']==1
    # The same exact normalized image should now be matched, with no remote AI.
    second=upload(client,{'X-Robot-Key':cfg.robot_api_key})
    assert second.status_code==201,second.text
    assert second.json()['status']=='recognized_candidate'
    assert second.json()['candidate_label']=='Agrafeuse'
    assert second.json()['confidence']==1
    assert client.post(f"/api/observations/{second.json()['id']}/confirm",
                       headers={'X-Robot-Key':cfg.robot_api_key},json={'label':'Agrafeuse'}).status_code==403
    assert client.get('/api/state',headers=headers).json()['stats']['concepts']==1
    assert client.delete(f"/api/observations/{obs['id']}",headers=headers).status_code==200
    assert client.get(obs['image_url'],headers=headers).status_code==404
    assert client.get(f'/api/concepts/{cid}',headers=headers).json()['example_count']==0
    assert client.delete(f'/api/concepts/{cid}',headers=headers).status_code==200
    s=client.get('/api/state',headers=headers).json()
    assert s['stats']['concepts']==0
    assert s['stats']['observations']==1
    assert s['observations'][0]['status']=='unknown'


def test_persistence_across_app_restart(env):
    client,headers,cfg=env
    photo=upload(client,headers,jpg('blue')).json()
    client.post(f"/api/observations/{photo['id']}/confirm",headers=headers,json={'label':'Boîte bleue'})
    # Recreate separate app/engine, same SQLite file and media directory.
    app2=create_app(cfg)
    with TestClient(app2) as c2:
        s=c2.get('/api/state',headers=headers).json()
        assert s['stats']['concepts']==1
        assert s['concepts'][0]['label']=='Boîte bleue'
        assert upload(c2,headers,jpg('blue')).json()['candidate_label']=='Boîte bleue'
    app2.state.engine.dispose()


def test_facts_curiosity_and_export(env):
    client,headers,_=env
    observation=upload(client,headers).json()
    curiosity=client.get('/api/curiosity',headers=headers).json()
    assert len(curiosity['tasks'])==1
    con=client.post(f"/api/observations/{observation['id']}/confirm",headers=headers,json={'label':'Papier'}).json()['concept']
    fact=client.post(f"/api/concepts/{con['id']}/facts",headers=headers,json={'text':'Une feuille peut être agrafée.'})
    assert fact.status_code==200
    assert client.get('/api/state',headers=headers).json()['stats']['verified_facts']==1
    export=client.get('/api/export',headers=headers)
    assert export.status_code==200
    assert export.json()['concepts'][0]['label']=='Papier'
    assert 'images' in export.json()['warning'].lower()


def test_invalid_secrets():
    with pytest.raises(ValueError):
        Settings(database_url='sqlite:///:memory:', data_dir=Path('/tmp'),admin_user='admin',
                 admin_password='CHANGE_ME', robot_api_key='x'*32).validate()


def test_remote_vision_is_unconfirmed_proposal(tmp_path, monkeypatch):
    from lifeai import app as lifeapp
    monkeypatch.setattr(lifeapp, 'remote_proposal',
                        lambda *_: {'label':'Agrafeuse','category':'papeterie',
                                    'description':'Un outil de bureau','confidence':0.93})
    cfg=Settings(database_url=f'sqlite:///{tmp_path / "vision.sqlite3"}',
                 data_dir=tmp_path/'media',admin_user='admin',
                 admin_password='test-admin-password-example',
                 robot_api_key='test-robot-api-key-123456789123456',
                 openai_api_key='fake-for-offline-test',auto_vision=True)
    app=create_app(cfg)
    headers={'Authorization':'Basic '+base64.b64encode(b'admin:test-admin-password-example').decode()}
    with TestClient(app) as client:
        oid=upload(client,headers).json()['id']
        # TestClient waits for the background task to complete.
        result=client.get('/api/state',headers=headers).json()
        assert result['observations'][0]['id']==oid
        assert result['observations'][0]['status']=='proposed'
        assert result['observations'][0]['candidate_label']=='Agrafeuse'
        assert result['stats']['concepts']==0  # no silent verification
    app.state.engine.dispose()


def test_wikipedia_fact_needs_review(env, monkeypatch):
    import httpx
    from lifeai import app as lifeapp
    client,headers,_=env
    observation=upload(client,headers).json()
    cid=client.post(f"/api/observations/{observation['id']}/confirm",headers=headers,
                    json={'label':'Agrafeuse'}).json()['concept']['id']
    def fake_get(url,**kwargs):
        assert url=='https://fr.wikipedia.org/w/api.php'
        assert kwargs['params']['titles']=='Agrafeuse'
        req=httpx.Request('GET',url)
        return httpx.Response(200,json={'query':{'pages':{'123':{'pageid':123,'title':'Agrafeuse',
                                      'extract':'Une agrafeuse sert à assembler des feuilles.'}}}},request=req)
    monkeypatch.setattr(lifeapp.httpx,'get',fake_get)
    res=client.post(f'/api/concepts/{cid}/research',headers=headers)
    assert res.status_code==200,res.text
    assert res.json()['status']=='to_review'
    assert client.get('/api/state',headers=headers).json()['stats']['verified_facts']==0
    check=client.post(f"/api/facts/{res.json()['id']}/review",headers=headers,json={'approve':True})
    assert check.status_code==200
    assert client.get('/api/state',headers=headers).json()['stats']['verified_facts']==1
