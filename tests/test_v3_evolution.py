"""Self-evolution validation: all tests work offline, no provider or motor calls."""
import ast
import base64
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from lifeai.app import create_app
from lifeai.config import Settings
from lifeai.db import session
from lifeai.evolution import evaluate_rules, proposal_json
from lifeai.models import Fact, Concept, ImprovementProposal, Observation
from tools.create_candidate import draft_candidate, ROOT
import io
from PIL import Image, ImageDraw

def photo(shape='rect'):
    im=Image.new('RGB',(240,180),'#eeeeee')
    draw=ImageDraw.Draw(im)
    if shape=='rect': draw.rectangle((28,30,175,150),fill='#ff451a')
    elif shape=='angled': draw.polygon([(40,85),(140,25),(211,75),(162,158)],fill='#ff451a')
    else: draw.ellipse((25,26,195,150),fill='#2789e9')
    out=io.BytesIO();im.save(out,'JPEG',quality=90);return out.getvalue()

def post_image(client,headers,content):
    return client.post('/api/observations',files={'file':('test.jpg',content,'image/jpeg')},headers=headers)


@pytest.fixture()
def env(tmp_path):
    cfg = Settings(database_url=f'sqlite:///{tmp_path / "v3.sqlite3"}',
                   data_dir=tmp_path/'media', admin_user='admin',
                   admin_password='v3-admin-password-example',
                   robot_api_key='v3-robot-key-1234567890123456789',
                   allow_wikipedia=False, openai_api_key='')
    app = create_app(cfg)
    admin = {'Authorization': 'Basic ' + base64.b64encode(b'admin:v3-admin-password-example').decode()}
    robot = {'X-Robot-Key': cfg.robot_api_key}
    with TestClient(app) as client:
        yield client, admin, robot, app, cfg
    app.state.engine.dispose()


def test_admin_only_and_no_motor_apis(env):
    c, admin, robot, app, _ = env
    for path in ['/api/evolution', '/api/evolution/diagnose']:
        method = c.post if path.endswith('diagnose') else c.get
        assert method(path).status_code == 401
        assert method(path, headers=robot).status_code == 403
    assert c.get('/api/evolution', headers=admin).json()['motor_control'] is False
    for url in ['/api/motors', '/api/servo', '/api/robot/move']:
        assert c.post(url, headers=admin).status_code == 404


def test_empty_diagnosis_is_idempotent_and_persistent(env):
    c, admin, _, app, cfg = env
    a = c.post('/api/evolution/diagnose', headers=admin)
    assert a.status_code == 200
    assert a.json()['proposals_created'] == 0
    b = c.post('/api/evolution/diagnose', headers=admin).json()
    assert b['status'] == 'already_run_today'
    assert b['run']['id'] == a.json()['run']['id']
    view = c.get('/api/evolution', headers=admin).json()
    assert len(view['runs']) == 1 and view['proposals'] == []
    # Import existing DB with new app instance: migration creates additive tables.
    app2 = create_app(cfg)
    with TestClient(app2) as c2:
        assert len(c2.get('/api/evolution', headers=admin).json()['runs']) == 1
    app2.state.engine.dispose()


def test_corrected_labels_produce_reviewable_improvement(env):
    c, admin, robot, app, _ = env
    for shape in ('rect','ellipse'):
        o=post_image(c, admin, photo(shape)).json()
        with session(app.state.engine) as db:
            found=db.get(Observation, o['id'])
            found.candidate_label='Agrafeuse'
            found.status='proposed'
            db.commit()
        assert c.post(f'/api/observations/{o["id"]}/confirm', headers=admin,
                      json={'label':'Perforatrice'}).status_code == 200
    analysis = c.post('/api/evolution/diagnose', headers=admin).json()
    assert analysis['run']['summary']['vision_corrected']==2
    proposals=c.get('/api/evolution', headers=admin).json()['proposals']
    p=next(x for x in proposals if x['rule_id']=='visual_misidentification')
    assert p['status']=='proposed' and 'lifeai/multiview.py' in p['suggested_paths']
    assert c.post(f'/api/evolution/proposals/{p["id"]}/review',headers=robot,
                  json={'approve':True}).status_code == 403
    code_before=hashlib.sha256((ROOT/'lifeai/multiview.py').read_bytes()).hexdigest()
    r=c.post(f'/api/evolution/proposals/{p["id"]}/review',headers=admin,
             json={'approve':True})
    assert r.status_code==200
    assert r.json()['status']=='approved_for_development'
    assert c.post(f'/api/evolution/proposals/{p["id"]}/review',headers=admin,
                  json={'approve':False}).status_code == 409
    brief=c.get(f'/api/evolution/proposals/{p["id"]}/brief',headers=admin)
    assert brief.status_code==200
    assert 'ne jamais' in brief.text.lower()
    assert 'Life AI V3' in brief.text
    assert hashlib.sha256((ROOT/'lifeai/multiview.py').read_bytes()).hexdigest()==code_before


def test_unknown_images_generate_a_bounded_proposal(env):
    c,admin,_,app,_=env
    for shape in ('rect','ellipse','angled'):
        assert post_image(c,admin,photo(shape)).status_code==201
    r=c.post('/api/evolution/diagnose',headers=admin).json()
    assert r['proposals_created'] == 1
    assert r['run']['findings'][0]['rule_id']=='unknown_object_queue'
    assert r['run']['summary']['unknown_observations']==3


def test_rules_do_not_treat_low_evidence_as_accuracy_claim():
    m = {'vision_corrected':0,'unknown_observations':0,'analysis_errors':0,
         'facts_to_review':0,'confirmed_concepts':0,'confirmed_examples':0}
    assert evaluate_rules(m)==[]
    m['facts_to_review']=3
    findings=evaluate_rules(m)
    assert len(findings)==1
    assert findings[0]['suggested_paths']==[]


def test_rejection_and_robot_does_not_receive_internal_proposals(env):
    c,admin,robot,app,_=env
    for shape in ('rect','ellipse','angled'):
        post_image(c,admin,photo(shape))
    c.post('/api/evolution/diagnose',headers=admin)
    p=c.get('/api/evolution',headers=admin).json()['proposals'][0]
    result=c.post(f'/api/evolution/proposals/{p["id"]}/review',headers=admin,
                  json={'approve':False}).json()
    assert result['status']=='rejected'
    body=c.get('/api/robot/knowledge',headers=robot).json()
    assert 'improvement_proposals' not in body
    assert 'diagnosis_runs' not in body


def test_draft_code_candidate_never_executes_or_overwrites(tmp_path):
    p=ImprovementProposal(id=str(uuid4()),rule_id='visual_misidentification',
        title='Corriger reconnaissance',explanation='Erreur constatée', priority='high',
        status='approved_for_development', suggested_paths=['lifeai/multiview.py'],
        evidence={'corrections_30j':3},acceptance_criteria=['Ne pas réécrire les moteurs.'])
    source=ROOT/'lifeai/multiview.py'
    original=source.read_text(encoding='utf-8')
    prehash=hashlib.sha256(source.read_bytes()).hexdigest()
    def fake_provider(prompt):
        assert 'multiview.py' in prompt
        return original+'\n# Draft review marker, not executed.\n'
    with pytest.raises(ValueError,match='Consentement'):
        draft_candidate(p,'lifeai/multiview.py',consent=False,api_key='',model='mock',
                        output_dir=tmp_path,provider=fake_provider)
    with pytest.raises(ValueError,match='périmètre'):
        draft_candidate(p,'lifeai/config.py',consent=True,api_key='',model='mock',
                        output_dir=tmp_path,provider=fake_provider)
    output=draft_candidate(p,'lifeai/multiview.py',consent=True,api_key='',model='mock',
                           output_dir=tmp_path,provider=fake_provider)
    assert (output/'proposal.patch').is_file()
    assert 'Draft review marker' in (output/'proposal.patch').read_text()
    assert (output/'manifest.json').is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==prehash
    with pytest.raises(FileExistsError):
        draft_candidate(p,'lifeai/multiview.py',consent=True,api_key='',model='mock',
                        output_dir=tmp_path,provider=fake_provider)


def test_candidate_rejects_invalid_syntax(tmp_path):
    p=ImprovementProposal(id=str(uuid4()),rule_id='vision_unavailability',
        title='Corriger analyse',explanation='Erreur',priority='medium',
        status='approved_for_development',suggested_paths=['lifeai/vision.py'],
        evidence={},acceptance_criteria=[])
    with pytest.raises(SyntaxError):
        draft_candidate(p,'lifeai/vision.py',consent=True,api_key='',model='mock',
                        output_dir=tmp_path,provider=lambda _: 'def evil(:\n'+'x'*200)
    assert not list(tmp_path.glob('*/proposal.patch'))
