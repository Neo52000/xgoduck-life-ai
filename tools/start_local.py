#!/usr/bin/env python3
"""Run the local Life AI demo. Requires dependencies and a generated .env."""
from pathlib import Path
import os
import sys
from dotenv import load_dotenv
import uvicorn

project=Path(__file__).resolve().parents[1]
os.chdir(project)
sys.path.insert(0, str(project))
if not (project/'.env').exists():
    sys.exit('Configuration absente : lance python tools/init_local.py')
load_dotenv(project/'.env',override=False)
print('Life AI local : http://127.0.0.1:8000')
print('Arrêt : Ctrl+C')
uvicorn.run('lifeai.app:app', host='127.0.0.1', port=8000, reload=False)
