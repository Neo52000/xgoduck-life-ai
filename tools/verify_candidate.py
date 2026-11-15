"""Manually-authorized candidate tests in an offline, unprivileged Docker container.

Run on a separate development computer. Never on the production VPS.
Requires explicit inspection of the generated patch before running.
"""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from lifeai.evolution import REVIEWABLE_CODE_PATHS

ROOT = Path(__file__).resolve().parents[1]


def verify(candidate_dir: Path, *, reviewed: bool, image: str = 'xgoduck-lifeai-tests:local') -> int:
    if not reviewed:
        raise ValueError('Tu dois relire le diff et donner --reviewed-diff avant de tester')
    meta_file = candidate_dir/'manifest.json'
    meta = json.loads(meta_file.read_text(encoding='utf-8'))
    rel = meta.get('file')
    if rel not in REVIEWABLE_CODE_PATHS:
        raise ValueError('Fichier hors liste blanche')
    if not meta.get('external_code_transmission_consented'):
        raise ValueError('Manifest incomplet')
    source_text = (candidate_dir/'candidate.py.txt').read_text(encoding='utf-8')
    ast.parse(source_text, filename=rel)
    with tempfile.TemporaryDirectory(prefix='lifeai-v3-review-') as temp:
        work = Path(temp)/'source'
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
            '.env','.git','.venv','.pytest_cache','__pycache__','*.pyc','data',
            '*.sqlite3','*.db','review_candidates','lifeai-review-candidates'))
        (work/rel).write_text(source_text, encoding='utf-8')
        env = ['-e','ADMIN_USER=test-admin','-e','ADMIN_PASSWORD=test-admin-password-example',
               '-e','ROBOT_API_KEY=test-robot-api-key-123456789123456',
               '-e','DATABASE_URL=sqlite:////tmp/lifeai_candidate_import.sqlite3',
               '-e','DATA_DIR=/tmp/lifeai_candidate_media',
               '-e','OPENAI_API_KEY=', '-e','AUTO_VISION=false',
               '-e','REMOTE_REFERENCE_MATCHING=false']
        cmd = ['docker','run','--rm','--network','none','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges',
            '--pids-limit','128','--memory','1g','--cpus','1',
            '--user','10001:10001','--tmpfs','/tmp:rw,noexec,nosuid,size=256m,mode=1777',
            '-v',f'{work}:/work:ro','-w','/work',*env,image,
            'python','-m','pytest','-q']
        # No shell; only Docker on an explicitly approved local dev computer.
        result = subprocess.run(cmd, check=False, timeout=240)
        return result.returncode


def main():
    ap=argparse.ArgumentParser(description='Vérifier un brouillon IA dans un conteneur éphémère hors réseau')
    ap.add_argument('--candidate-dir',required=True,type=Path)
    ap.add_argument('--reviewed-diff',action='store_true', help='Je certifie avoir relu manuellement ce diff')
    args=ap.parse_args()
    raise SystemExit(verify(args.candidate_dir,reviewed=args.reviewed_diff))

if __name__=='__main__':
    main()
