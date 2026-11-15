"""V3.3 continuous evolution: offline, deterministic, no code execution."""
from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from lifeai.app import create_app
from lifeai.config import Settings
from lifeai.continuous import (assess_release, compare_cycles, review_assessment,
    run_continuous_cycle, visual_benchmark)
from lifeai.db import session
from lifeai.models import (Concept, EvolutionCycle, Example, ImprovementProposal,
    Observation, ReleaseAssessment)


def ident():
    return str(uuid4())


@pytest.fixture
def db_app(tmp_path):
    cfg=Settings(database_url=f'sqlite:///{tmp_path / "memory.db"}',data_dir=tmp_path,
       admin_user='owner',admin_password='secret-example-for-tests',
       robot_api_key='robot-key-test-abcdefghijklmnop')
    app=create_app(cfg)
    return app, cfg


def seed_known(db):
    """Synthetic but consistent image feature vectors: 2 objects x 6 distinct views."""
    for i, label in enumerate(('agrafeuse', 'perforatrice')):
        concept_id=ident()
        db.add(Concept(id=concept_id,label=label,status='confirmed'))
        db.flush()
        for k in range(6):
            obs_id=ident()
            fingerprint=f'{i+1:02x}{k:02x}'.ljust(64,'0')
            dhash='0000000000000000' if i==0 else 'ffffffffffffffff'
            histogram=[float(i)]*24
            texture=[float(i)]*256
            db.add(Observation(id=obs_id,image_name='notneeded.jpg',sha256=fingerprint,
                dhash=dhash,histogram=histogram,texture=texture,status='learned'))
            db.flush()
            db.add(Example(id=ident(),concept_id=concept_id,observation_id=obs_id,
                sha256=fingerprint,dhash=dhash,histogram=histogram,texture=texture))
    db.commit()


def make_proposal(db):
    p=ImprovementProposal(id=ident(),rule_id='visual_misidentification',
        title='Améliorer reconnaissance',explanation='étudier',priority='medium',
        suggested_paths=['lifeai/vision.py'], evidence={'errors':2},
        acceptance_criteria=['conserver les validations'],
        status='approved_for_development')
    db.add(p);db.commit();return p


def auth():
    creds=base64.b64encode(b'owner:secret-example-for-tests').decode('ascii')
    return {'Authorization':'Basic '+creds}


def test_visual_benchmark_heldout_and_reproducible(db_app):
    app,_=db_app
    with session(app.state.engine) as db:
        seed_known(db)
        first=visual_benchmark(db)
        second=visual_benchmark(db)
        assert first==second
        assert first['unique_heldout_samples']==10
        assert first['correct']==10 and first['wrong']==0
        assert first['accuracy']==1.0
        assert first['coverage']==1.0
        assert first['sufficient_for_release'] is True
        assert len(first['dataset_sha256'])==64


def test_empty_or_one_class_is_inconclusive(db_app):
    app,_=db_app
    with session(app.state.engine) as db:
        result=visual_benchmark(db)
        assert result['unique_heldout_samples']==0
        assert result['accuracy'] is None
        assert not result['sufficient_for_release']
        assert result['precision_when_recognized'] is None


def test_cycle_idempotence_and_persistence(db_app):
    app,_=db_app
    today=datetime(2026,11,15,tzinfo=timezone.utc)
    with session(app.state.engine) as db:
        seed_known(db)
        result=run_continuous_cycle(db,revision='1.0.0',date_override=today)
        assert result['status']=='completed'
        assert result['cycle']['benchmark']['correct']==10
        dup=run_continuous_cycle(db,revision='1.0.0',date_override=today)
        assert dup['status']=='already_run_today'
        assert dup['cycle']['id']==result['cycle']['id']
    with session(app.state.engine) as db:
        rows=db.scalars(select(EvolutionCycle)).all()
        assert len(rows)==1
        later=run_continuous_cycle(db,revision='1.0.1',date_override=today+timedelta(days=1))
        assert later['status']=='completed'
        assert later['cycle']['trend']['benchmark_comparable']
        assert later['cycle']['trend']['accuracy_delta']==0.0
        assert later['cycle']['trend']['revision_changed']


def test_dataset_change_never_claims_progress(db_app):
    app,_=db_app
    with session(app.state.engine) as db:
        seed_known(db)
        initial=visual_benchmark(db)
        old=EvolutionCycle(id=ident(),day_key='2026-11-13',code_revision='v3.3.0',
            benchmark=initial,metrics={'vision_corrected':2},trend={})
        db.add(old);db.commit()
        example=db.scalars(select(Example)).first()
        example.sha256='f'*64
        db.commit()
        future=visual_benchmark(db)
        trend=compare_cycles(old,{'vision_corrected':3},future,'v3.3.1')
        assert not trend['benchmark_comparable']
        assert trend['accuracy_delta'] is None
        assert trend['changes']['vision_corrected']==1


def test_release_gate_and_human_review(db_app):
    app,_=db_app
    with session(app.state.engine) as db:
        seed_known(db)
        benchmark=visual_benchmark(db)
        ref=EvolutionCycle(id=ident(),day_key='2026-11-13',code_revision='commit-a',
            benchmark=benchmark,metrics={},trend={})
        cand=EvolutionCycle(id=ident(),day_key='2026-11-14',code_revision='commit-b',
            benchmark=benchmark,metrics={},trend={})
        db.add_all([ref,cand]);p=make_proposal(db)
        result=assess_release(db,proposal_id=p.id,baseline_id=ref.id,candidate_id=cand.id,
             tests_total=32,tests_passed=32,artifact_sha256='a'*64,
             security_review=True,rollback_prepared=True)
        assert result['verdict']=='eligible_for_human_review'
        assert result['evidence']['ci_provenance']=='operator_attested_not_cryptographically_verified'
        item=db.get(ReleaseAssessment,result['id'])
        assert item.status=='pending_review'
        approved=review_assessment(db,item,approve=True)
        assert approved['status']=='reviewed_for_manual_release'
        with pytest.raises(ValueError):review_assessment(db,item,approve=True)


def test_release_gate_rejects_mismatched_dataset_and_bad_ci(db_app):
    app,_=db_app
    with session(app.state.engine) as db:
        seed_known(db)
        base=visual_benchmark(db)
        changed={**base,'dataset_sha256':'c'*64,'accuracy':0.8,'wrong':2,'coverage':0.7}
        a=EvolutionCycle(id=ident(),day_key='2026-11-11',code_revision='v-a',benchmark=base,metrics={},trend={})
        b=EvolutionCycle(id=ident(),day_key='2026-11-12',code_revision='v-b',benchmark=changed,metrics={},trend={})
        db.add_all([a,b]);p=make_proposal(db)
        out=assess_release(db,proposal_id=p.id,baseline_id=a.id,candidate_id=b.id,
            tests_total=20,tests_passed=19,artifact_sha256='e'*64,
            security_review=False,rollback_prepared=False)
        assert out['verdict']=='insufficient_evidence'
        assert len(out['reasons'])>=4
        with pytest.raises(ValueError):review_assessment(db,db.get(ReleaseAssessment,out['id']),approve=True)
        with pytest.raises(ValueError):assess_release(db,proposal_id=p.id,baseline_id=a.id,candidate_id=b.id,
            tests_total=20,tests_passed=21,artifact_sha256='e'*64,security_review=True,rollback_prepared=True)


def test_admin_api_and_robot_access_denied(db_app):
    app,_=db_app
    robot={'X-Robot-Key':'robot-key-test-abcdefghijklmnop'}
    with TestClient(app) as client:
        assert client.get('/api/evolution/continuous',headers=robot).status_code==403
        assert client.post('/api/evolution/continuous/cycle',headers=robot).status_code==403
        assert client.get('/api/evolution/benchmark',headers=robot).status_code==403
        assert client.post('/api/evolution/releases/assess',headers=robot,json={}).status_code==403
        state=client.get('/api/evolution/continuous',headers=auth())
        assert state.status_code==200
        assert state.json()['auto_deploy'] is False
        assert state.json()['motor_control'] is False
        created=client.post('/api/evolution/continuous/cycle',headers=auth())
        assert created.status_code==200
        assert created.json()['cycle']['benchmark']['accuracy'] is None
        assert client.post('/api/evolution/continuous/cycle',headers=auth()).json()['status']=='already_run_today'
        assert client.get('/api/evolution/benchmark',headers=auth()).status_code==200
        assert client.post('/api/evolution/releases/nope/review',headers=auth(),json={'approve':True}).status_code==404


def test_no_motor_or_apply_endpoints(db_app):
    app,_=db_app
    paths={route.path for route in app.routes}
    assert not any(token in p for p in paths for token in ('/motors','/servos','/firmware','/execute','/deploy','/merge','/apply-patch'))
