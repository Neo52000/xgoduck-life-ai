"""V2 regressions: no network, no motor calls, no real API expense."""
from __future__ import annotations
import base64
import io
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from lifeai.app import create_app
from lifeai.config import Settings


def photo(shape='rect'):
    im=Image.new('RGB',(240,180),'#eeeeee')
    d=ImageDraw.Draw(im)
    if shape == 'rect':
        d.rectangle((28,30,175,150),fill='#ff451a')
    elif shape == 'angled':
        d.polygon([(40,85),(140,25),(211,75),(162,158)],fill='#ff451a')
    else:
        d.ellipse((25,26,195,150),fill='#2789e9')
    out=io.BytesIO();im.save(out,'JPEG',quality=90);return out.getvalue()


def post_image(c,h,img):
    return c.post('/api/observations',files={'file':('test.jpg',img,'image/jpeg')},headers=h)


@pytest.fixture()
def setup(tmp_path):
    cfg=Settings(database_url=f'sqlite:///{tmp_path / "v2.sqlite3"}',
      data_dir=tmp_path/'media',admin_user='admin',
      admin_password='v2-admin-password-example',
      robot_api_key='v2-robot-key-12345678901234567890',
      openai_api_key='mock-key-for-local-test',
      remote_reference_matching=True, auto_vision=False,
      max_reference_images=6, max_research_per_cycle=2)
    app=create_app(cfg)
    h={'Authorization':'Basic '+base64.b64encode(b'admin:v2-admin-password-example').decode()}
    with TestClient(app) as c:
        yield c,h,cfg
    app.state.engine.dispose()


def test_multiview_candidate_requires_confirmation_and_reuses_memory(setup,monkeypatch):
    from lifeai import app as module
    client,h,cfg=setup
    first=post_image(client,h,photo('rect')).json()
    c=client.post(f'/api/observations/{first["id"]}/confirm',headers=h,
      json={'label':'Bloc orange'}).json()['concept']
    different=post_image(client,h,photo('angled')).json()
    assert different['status']=='unknown'
    calls=[]
    def compare(image,references,key,model):
        calls.append(references)
        assert len(references)==1
        assert references[0].concept_id==c['id']
        assert image != references[0].jpeg
        return {'matched_id':c['id'],'label':'Bloc orange',
                'category':'objet','description':'Forme géométrique orangée','confidence':0.91}
    monkeypatch.setattr(module,'compare_references',compare)
    ans=client.post(f'/api/observations/{different["id"]}/analyze',headers=h)
    assert ans.status_code==200,ans.text
    assert ans.json()['status']=='recognized_candidate'
    assert ans.json()['candidate_id']==c['id']
    assert ans.json()['confidence']==0.91
    assert client.get('/api/state',headers=h).json()['stats']['concepts']==1
    assert client.get('/api/learning/report',headers=h).json()['confirmed_examples']==1
    assert client.post(f'/api/observations/{different["id"]}/confirm',headers=h,
         json={'label':'Bloc orange'}).status_code==200
    assert client.get('/api/learning/report',headers=h).json()['concepts_with_multiple_views']==1
    assert len(calls)==1


def test_exact_duplicates_are_not_multiplied(setup):
    client,h,_=setup
    photo1=post_image(client,h,photo()).json()
    cid=client.post(f'/api/observations/{photo1["id"]}/confirm',headers=h,json={'label':'Panneau'}).json()['concept']['id']
    photo2=post_image(client,h,photo()).json()
    assert photo2['candidate_id']==cid
    client.post(f'/api/observations/{photo2["id"]}/confirm',headers=h,json={'label':'Panneau'})
    assert client.get(f'/api/concepts/{cid}',headers=h).json()['example_count']==1


def test_knowledge_sync_exposes_only_verified_facts(setup):
    client,h,cfg=setup
    first=post_image(client,h,photo()).json()
    cid=client.post(f'/api/observations/{first["id"]}/confirm',headers=h,json={'label':'Objet orange'}).json()['concept']['id']
    fid=client.post(f'/api/concepts/{cid}/facts',headers=h,json={'text':'Un objet orange existe.'}).json()['id']
    k=client.get('/api/robot/knowledge',headers={'X-Robot-Key':cfg.robot_api_key})
    assert k.status_code==200 and k.json()['schema_version']==2
    assert len(k.json()['concepts'][0]['facts'])==1
    assert client.get('/api/robot/knowledge').status_code==401
    assert client.post('/api/learning/cycle',headers={'X-Robot-Key':cfg.robot_api_key}).status_code==403


def test_bounded_daily_research_cycle_and_review(setup,monkeypatch):
    from lifeai import app as module
    c,h,_=setup
    for label,kind in [('Agrafeuse','rect'),('Papier','ellipse'),('Stylo','angled')]:
        o=post_image(c,h,photo(kind)).json()
        assert c.post(f'/api/observations/{o["id"]}/confirm',headers=h,json={'label':label}).status_code==200
    requests=[]
    def fake_get(url,**kwargs):
        assert url == 'https://fr.wikipedia.org/w/api.php'
        name=kwargs['params']['titles'];requests.append(name)
        req=httpx.Request('GET',url)
        return httpx.Response(200,request=req,json={'query':{'pages':{'1':{
          'pageid':1,'title':name,'extract':f'Information sur {name}.'}}}})
    monkeypatch.setattr(module.httpx,'get',fake_get)
    res=c.post('/api/learning/cycle',headers=h)
    assert res.status_code==200,res.text
    assert res.json()['processed']==2
    assert len(requests)==2
    again=c.post('/api/learning/cycle',headers=h).json()
    assert again['status']=='already_run_today'
    state=c.get('/api/state',headers=h).json()
    assert state['stats']['pending_facts']==2
    k=c.get('/api/robot/knowledge',headers=h).json()
    assert all(not item['facts'] for item in k['concepts'])
    f=next(z for z in state['facts'] if z['status']=='to_review')
    c.post(f'/api/facts/{f["id"]}/review',headers=h,json={'approve':True})
    k2=c.get('/api/robot/knowledge',headers=h).json()
    assert sum(len(item['facts']) for item in k2['concepts'])==1


def test_multiview_invalid_concept_id_is_discarded(monkeypatch):
    import sys,types
    from lifeai.multiview import VisualReference, compare_references
    class Response:
        output_text='{"matched_id":"untrusted-id","label":"Inconnu","confidence":0.99}'
    class FakeResponses:
        def create(self,**kwargs):
            assert len(kwargs['input'][0]['content'])==5
            return Response()
    class OpenAI:
        def __init__(self,**kwargs): self.responses=FakeResponses()
    monkeypatch.setitem(sys.modules,'openai',types.SimpleNamespace(OpenAI=OpenAI))
    x=compare_references(b'fakejpg',[VisualReference('trusted-id','Agrafeuse',b'refjpg')], 'fake', 'mock')
    assert x['matched_id']==''
